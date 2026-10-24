package http

import (
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"
	"unicode/utf8"

	"github.com/jackc/pgx/v5"
	"golang.org/x/crypto/bcrypt"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
)

// Email and password sign-in. Only the website calls these: each call carries an API token the website signed with
// AUTH_SECRET for the email being registered or signed in, so no other caller can use them. Passwords and hashes are
// never logged or returned, and every refusal of a sign-in says the same thing.

const (
	minPassword  = 8
	maxPassword  = 128
	bcryptCost   = 12
	failLimit    = 5
	failWindow   = 15 * time.Minute
	clientIPName = "X-Talnex-Client-Ip" // the visitor's address, set by the website (the API only sees the website)
)

const wrongLogin = "email or password is wrong"

// hashPassword is bcrypt of the password's SHA-256, so the whole password counts even past bcrypt's 72 bytes.
func hashPassword(password string) (string, error) {
	h, err := bcrypt.GenerateFromPassword(prehash(password), bcryptCost)
	return string(h), err
}

func prehash(password string) []byte {
	sum := sha256.Sum256([]byte(password))
	return []byte(base64.StdEncoding.EncodeToString(sum[:]))
}

// dummyHash is checked when there is no account, so a missing email takes as long as a wrong password.
var dummyHash, _ = bcrypt.GenerateFromPassword(prehash("not a real password"), bcryptCost)

func passwordProblem(p string) string {
	if n := utf8.RuneCountInString(p); n < minPassword || n > maxPassword {
		return "the password must be 8 to 128 characters"
	}
	return ""
}

// failLimiter counts failed attempts per key (an email or a visitor's address) inside a sliding window.
// ponytail: in memory, per API process; move to Postgres or Redis if the API runs on several machines.
type failLimiter struct {
	mu    sync.Mutex
	fails map[string][]time.Time
}

func (l *failLimiter) blocked(key string, now time.Time) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	return len(l.recent(key, now)) >= failLimit
}

func (l *failLimiter) fail(key string, now time.Time) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.fails[key] = append(l.recent(key, now), now)
}

func (l *failLimiter) clear(key string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	delete(l.fails, key)
}

func (l *failLimiter) recent(key string, now time.Time) []time.Time {
	if l.fails == nil {
		l.fails = map[string][]time.Time{}
	}
	kept := l.fails[key][:0]
	for _, t := range l.fails[key] {
		if now.Sub(t) < failWindow {
			kept = append(kept, t)
		}
	}
	return kept
}

func visitor(r *http.Request) string {
	if ip := strings.TrimSpace(r.Header.Get(clientIPName)); ip != "" && len(ip) <= 64 {
		return "ip:" + ip
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		host = r.RemoteAddr
	}
	return "ip:" + host
}

type passwordBody struct {
	Password string `json:"password"`
}

// register sets a password on the signed-in email (the token's role is its door, checked by the sign-in middleware).
// An email that already has a password is refused: the person signs in instead.
func (s *server) register(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	now := time.Now()
	ip := visitor(r)
	if s.logins.blocked(ip, now) {
		writeError(w, http.StatusTooManyRequests, "too many tries; wait a few minutes and try again")
		return
	}
	if who.Role == "" {
		writeError(w, http.StatusBadRequest, "choose recruiter or organizer to create an account")
		return
	}
	var in passwordBody
	if !decode(w, r, &in) {
		return
	}
	if p := passwordProblem(in.Password); p != "" {
		writeError(w, http.StatusBadRequest, p)
		return
	}
	hash, err := hashPassword(in.Password)
	if err != nil {
		s.fail(w, "hash password", err)
		return
	}
	tag, err := s.opts.Pool.Exec(r.Context(),
		`UPDATE users SET password_hash = $2 WHERE id = $1::uuid AND password_hash IS NULL`, who.UserID, hash)
	if err != nil {
		s.fail(w, "save password", err)
		return
	}
	if tag.RowsAffected() == 0 {
		s.logins.fail(ip, now) // many tries on taken emails from one address look like probing
		writeError(w, http.StatusConflict, "this email already has an account; sign in instead")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]string{"email": who.Email, "role": who.Role})
}

// passwordLogin checks an email and password. It is outside the sign-in middleware so a wrong email never creates
// an account, but it still needs a website-signed token naming the email.
func (s *server) passwordLogin(w http.ResponseWriter, r *http.Request) {
	token, _ := strings.CutPrefix(r.Header.Get("Authorization"), "Bearer ")
	email, _, _, err := auth.VerifyWithRole(s.opts.AuthSecret, token)
	if token == "" || err != nil {
		writeError(w, http.StatusUnauthorized, "sign in required")
		return
	}
	now := time.Now()
	byEmail, byIP := "email:"+strings.ToLower(email), visitor(r)
	if s.logins.blocked(byEmail, now) || s.logins.blocked(byIP, now) {
		writeError(w, http.StatusTooManyRequests, "too many tries; wait a few minutes and try again")
		return
	}
	var in passwordBody
	if !decode(w, r, &in) {
		return
	}
	var name, role string
	var hash *string
	err = s.opts.Pool.QueryRow(r.Context(),
		`SELECT coalesce(name, ''), coalesce(role, ''), password_hash FROM users WHERE email = $1`, email).
		Scan(&name, &role, &hash)
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		s.fail(w, "read account", err)
		return
	}
	stored := dummyHash
	if hash != nil {
		stored = []byte(*hash)
	}
	match := bcrypt.CompareHashAndPassword(stored, prehash(in.Password)) == nil
	if hash == nil || !match || passwordProblem(in.Password) != "" {
		s.logins.fail(byEmail, now)
		s.logins.fail(byIP, now)
		writeError(w, http.StatusUnauthorized, wrongLogin)
		return
	}
	s.logins.clear(byEmail)
	writeJSON(w, http.StatusOK, map[string]string{"email": email, "name": name, "role": role})
}
