package config

import (
	"strings"
	"testing"
)

func clearEnv(t *testing.T) {
	t.Helper()
	for _, k := range []string{
		"DATABASE_URL", "S3_ENDPOINT", "S3_REGION", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY",
		"AUTH_SECRET", "WEB_ORIGIN", "API_PORT", "ENABLE_DEV_ENDPOINTS", "MIGRATIONS_DIR", "SMS_GATEWAY_KEY",
	} {
		t.Setenv(k, "")
	}
}

func TestLoadAPIListsEveryMissingSetting(t *testing.T) {
	clearEnv(t)
	_, err := LoadAPI()
	if err == nil {
		t.Fatal("expected an error")
	}
	for _, name := range []string{"DATABASE_URL", "S3_BUCKET", "AUTH_SECRET", "WEB_ORIGIN"} {
		if !strings.Contains(err.Error(), name) {
			t.Errorf("error should name %s: %v", name, err)
		}
	}
}

func TestLoadAPIAcceptsFullSettings(t *testing.T) {
	clearEnv(t)
	t.Setenv("DATABASE_URL", "postgres://u:p@h:5432/d")
	t.Setenv("S3_ENDPOINT", "http://minio:9000")
	t.Setenv("S3_REGION", "auto")
	t.Setenv("S3_BUCKET", "talnex")
	t.Setenv("S3_ACCESS_KEY", "a")
	t.Setenv("S3_SECRET_KEY", "b")
	t.Setenv("AUTH_SECRET", "0123456789abcdef")
	t.Setenv("WEB_ORIGIN", "http://localhost:3000")
	c, err := LoadAPI()
	if err != nil {
		t.Fatal(err)
	}
	if c.API.Port != 8080 || c.Storage.ViewLinkTTL.Seconds() != 300 {
		t.Errorf("defaults not applied: %+v", c)
	}
}

func TestShortAuthSecretRejected(t *testing.T) {
	clearEnv(t)
	t.Setenv("DATABASE_URL", "x")
	t.Setenv("S3_ENDPOINT", "http://minio:9000")
	t.Setenv("S3_REGION", "auto")
	t.Setenv("S3_BUCKET", "b")
	t.Setenv("S3_ACCESS_KEY", "a")
	t.Setenv("S3_SECRET_KEY", "b")
	t.Setenv("AUTH_SECRET", "short")
	t.Setenv("WEB_ORIGIN", "http://localhost:3000")
	if _, err := LoadAPI(); err == nil || !strings.Contains(err.Error(), "AUTH_SECRET") {
		t.Fatalf("expected AUTH_SECRET error, got %v", err)
	}
}

func TestSMSGatewayKeyIsOptionalButNotShort(t *testing.T) {
	clearEnv(t)
	t.Setenv("DATABASE_URL", "postgres://u:p@h:5432/d")
	t.Setenv("S3_ENDPOINT", "http://minio:9000")
	t.Setenv("S3_REGION", "auto")
	t.Setenv("S3_BUCKET", "talnex")
	t.Setenv("S3_ACCESS_KEY", "a")
	t.Setenv("S3_SECRET_KEY", "b")
	t.Setenv("AUTH_SECRET", "0123456789abcdef")
	t.Setenv("WEB_ORIGIN", "http://localhost:3000")
	if _, err := LoadAPI(); err != nil {
		t.Fatalf("empty key must be allowed: %v", err)
	}
	t.Setenv("SMS_GATEWAY_KEY", "short")
	if _, err := LoadAPI(); err == nil || !strings.Contains(err.Error(), "SMS_GATEWAY_KEY") {
		t.Fatalf("short key must be rejected: %v", err)
	}
	t.Setenv("SMS_GATEWAY_KEY", "0123456789abcdef")
	if c, err := LoadAPI(); err != nil || c.API.SMSGatewayKey == "" {
		t.Fatalf("good key: %v", err)
	}
}
