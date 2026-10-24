package http_test

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log/slog"
	nethttp "net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/cleanup"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	apihttp "github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/http"
)

const gatewayKey = "gateway-key-0123456789"

func smsServer(t *testing.T, key string) *httptest.Server {
	t.Helper()
	h := apihttp.NewHandler(apihttp.Options{
		Pool: dbtest.Pool(t), AuthSecret: secret, WebOrigin: "http://localhost:3000", SMSGatewayKey: key,
		Log: slog.New(slog.NewTextHandler(io.Discard, nil)),
	})
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	return srv
}

func postSMS(t *testing.T, base, key, body string) int {
	t.Helper()
	req, _ := nethttp.NewRequest("POST", base+"/v1/sms/incoming", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	if key != "" {
		req.Header.Set("X-Gateway-Key", key)
	}
	resp, err := nethttp.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	return resp.StatusCode
}

func goodSMS(body string) string {
	return fmt.Sprintf(`{"from":"ACME","body":%q,"received_at":%q,"device":"phone1"}`, body, time.Now().UTC().Format(time.RFC3339))
}

func clearSMS(t *testing.T) {
	t.Helper()
	if _, err := dbtest.Pool(t).Exec(context.Background(), `DELETE FROM inbound_sms`); err != nil {
		t.Fatal(err)
	}
}

func TestSMSRouteIsAGatewayRouteNotAUserRoute(t *testing.T) {
	src, _ := os.ReadFile("server.go")
	if strings.Contains(string(src), `private.HandleFunc("POST /v1/sms/incoming"`) {
		t.Fatal("the phone route must not sit behind user sign-in")
	}
	if !strings.Contains(string(src), `root.HandleFunc("POST /v1/sms/incoming"`) {
		t.Fatal("the gateway route is not registered")
	}
}

func TestSMSSwitchedOffWithoutKey(t *testing.T) {
	srv := smsServer(t, "")
	if c := postSMS(t, srv.URL, "anything-at-all-123456", goodSMS("code 123456")); c != 503 {
		t.Fatalf("want 503, got %d", c)
	}
	if c := postSMS(t, srv.URL, "", goodSMS("code 123456")); c != 503 {
		t.Fatalf("want 503, got %d", c)
	}
}

func TestSMSAuthAndValidation(t *testing.T) {
	clearSMS(t)
	srv := smsServer(t, gatewayKey)
	future := time.Now().Add(time.Hour).UTC().Format(time.RFC3339)
	cases := []struct {
		name, key, body string
		want            int
	}{
		{"no key", "", goodSMS("x"), 401},
		{"wrong key", "gateway-key-wrong-00000", goodSMS("x"), 401},
		{"good", gatewayKey, goodSMS("Your code is 482913"), 202},
		{"not json", gatewayKey, `nope`, 400},
		{"empty body", gatewayKey, `{"from":"A","body":"","received_at":"` + future + `"}`, 400},
		{"empty from", gatewayKey, `{"from":"","body":"x","received_at":"2026-01-01T00:00:00Z"}`, 400},
		{"bad time", gatewayKey, `{"from":"A","body":"x","received_at":"yesterday"}`, 400},
		{"future time", gatewayKey, `{"from":"A","body":"x","received_at":"` + future + `"}`, 400},
		{"too long", gatewayKey, goodSMS(strings.Repeat("a", 1001)), 400},
		{"max length ok", gatewayKey, goodSMS(strings.Repeat("a", 1000)), 202},
		{"over 8KB", gatewayKey, goodSMS(strings.Repeat("a", 9000)), 400},
	}
	for _, c := range cases {
		if got := postSMS(t, srv.URL, c.key, c.body); got != c.want {
			t.Errorf("%s: want %d, got %d", c.name, c.want, got)
		}
	}
	var n int
	if err := dbtest.Pool(t).QueryRow(context.Background(), `SELECT count(*) FROM inbound_sms`).Scan(&n); err != nil || n != 2 {
		t.Fatalf("want 2 saved rows, got %d (%v)", n, err)
	}
}

func TestSMSRateLimit(t *testing.T) {
	clearSMS(t)
	srv := smsServer(t, gatewayKey)
	got429 := false
	for i := 0; i < 70; i++ {
		if postSMS(t, srv.URL, gatewayKey, goodSMS("hello")) == 429 {
			got429 = true
			break
		}
	}
	if !got429 {
		t.Fatal("expected a 429 after 60 messages in a minute")
	}
}

func TestPurgeOldSMSAndOpportunisticPurge(t *testing.T) {
	clearSMS(t)
	pool := dbtest.Pool(t)
	ctx := context.Background()
	_, err := pool.Exec(ctx, `INSERT INTO inbound_sms (from_number, body, received_at, created_at) VALUES
		('A','old', now() - interval '30 hours', now() - interval '30 hours'),
		('A','fresh', now(), now())`)
	if err != nil {
		t.Fatal(err)
	}
	srv := smsServer(t, gatewayKey)
	if c := postSMS(t, srv.URL, gatewayKey, goodSMS("new")); c != 202 {
		t.Fatalf("want 202 got %d", c)
	}
	var old int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM inbound_sms WHERE body='old'`).Scan(&old)
	if old != 0 {
		t.Fatal("old message should be purged on the next request")
	}
	n, err := cleanup.PurgeOldSMS(ctx, pool, 0)
	if err != nil || n < 2 {
		t.Fatalf("purge with zero age should clear the rest: %d %v", n, err)
	}
}
