package http

import (
	"context"
	"crypto/subtle"
	"encoding/json"
	"net/http"
	"sync"
	"time"
	"unicode/utf8"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/cleanup"
)

const (
	smsBodyLimit     = 8 * 1024
	smsTextMax       = 1000
	smsFutureSlack   = 5 * time.Minute
	smsKeepFor       = 24 * time.Hour
	smsMaxPerMinute  = 60
	smsFieldMax      = 100
	smsMinKeyLength  = 16
	smsSwitchedOffMs = "phone sign-up is switched off"
)

// smsLimiter allows at most smsMaxPerMinute messages per rolling minute, overall.
type smsLimiter struct {
	mu    sync.Mutex
	times []time.Time
}

func (l *smsLimiter) allow(now time.Time) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	cut := now.Add(-time.Minute)
	kept := l.times[:0]
	for _, t := range l.times {
		if t.After(cut) {
			kept = append(kept, t)
		}
	}
	l.times = kept
	if len(l.times) >= smsMaxPerMinute {
		return false
	}
	l.times = append(l.times, now)
	return true
}

// incomingSMS receives one text message from the team phone. The phone has no user, so this route is NOT behind
// the sign-in check: it is protected only by the gateway key header, compared in constant time.
// The message text and the key are never logged.
func (s *server) incomingSMS(w http.ResponseWriter, r *http.Request) {
	key := s.opts.SMSGatewayKey
	if len(key) < smsMinKeyLength {
		writeError(w, http.StatusServiceUnavailable, smsSwitchedOffMs)
		return
	}
	got := r.Header.Get("X-Gateway-Key")
	if subtle.ConstantTimeCompare([]byte(got), []byte(key)) != 1 {
		writeError(w, http.StatusUnauthorized, "wrong gateway key")
		return
	}

	// Old messages are personal data: clear them whenever one arrives. A failure here must not lose the new message.
	purgeCtx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	if _, err := cleanup.PurgeOldSMS(purgeCtx, s.opts.Pool, smsKeepFor); err != nil {
		s.opts.Log.Warn("could not clear old text messages", "err", err)
	}
	cancel()

	if !s.sms.allow(time.Now()) {
		writeError(w, http.StatusTooManyRequests, "too many messages, slow down")
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, smsBodyLimit)
	var in struct {
		From       string `json:"from"`
		Body       string `json:"body"`
		ReceivedAt string `json:"received_at"`
		Device     string `json:"device"`
	}
	dec := json.NewDecoder(r.Body)
	if err := dec.Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "the message could not be read")
		return
	}
	if in.From == "" || in.Body == "" {
		writeError(w, http.StatusBadRequest, "from and body are required")
		return
	}
	if utf8.RuneCountInString(in.Body) > smsTextMax || utf8.RuneCountInString(in.From) > smsFieldMax ||
		utf8.RuneCountInString(in.Device) > smsFieldMax {
		writeError(w, http.StatusBadRequest, "a field is too long")
		return
	}
	at, err := time.Parse(time.RFC3339, in.ReceivedAt)
	if err != nil {
		writeError(w, http.StatusBadRequest, "received_at must be an ISO 8601 time")
		return
	}
	if at.After(time.Now().Add(smsFutureSlack)) {
		writeError(w, http.StatusBadRequest, "received_at is in the future")
		return
	}

	var device any
	if in.Device != "" {
		device = in.Device
	}
	if _, err := s.opts.Pool.Exec(r.Context(),
		`INSERT INTO inbound_sms (from_number, body, device, received_at) VALUES ($1, $2, $3, $4)`,
		in.From, in.Body, device, at.UTC()); err != nil {
		s.opts.Log.Error("could not save a text message", "err", err)
		writeError(w, http.StatusInternalServerError, "could not save the message")
		return
	}
	w.WriteHeader(http.StatusAccepted)
}
