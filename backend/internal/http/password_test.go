package http_test

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestPasswordRegisterAndLogin(t *testing.T) {
	srv, pool, _ := setupProgress(t)
	email := "pw-" + uuid.NewString()[:8] + "@example.com"
	const pw = "correct horse battery"

	// Registration needs a door (a role) and a long enough password.
	if code, _ := roleCall(t, srv.URL, "POST", "/v1/auth/register", email, "", map[string]any{"password": pw}); code != 400 {
		t.Fatalf("register without a role = %d, want 400", code)
	}
	if code, _ := roleCall(t, srv.URL, "POST", "/v1/auth/register", email, "recruiter", map[string]any{"password": "short"}); code != 400 {
		t.Fatalf("short password = %d, want 400", code)
	}
	code, out := roleCall(t, srv.URL, "POST", "/v1/auth/register", email, "recruiter", map[string]any{"password": pw})
	if code != 201 || strings.Contains(out, "hash") || strings.Contains(out, pw) {
		t.Fatalf("register = %d %s", code, out)
	}
	// The hash is bcrypt, never the password itself.
	var hash string
	if err := pool.QueryRow(context.Background(), `SELECT password_hash FROM users WHERE email = $1`, email).Scan(&hash); err != nil ||
		!strings.HasPrefix(hash, "$2") || strings.Contains(hash, pw) {
		t.Fatalf("stored hash = %q (%v)", hash, err)
	}
	if code, _ := roleCall(t, srv.URL, "POST", "/v1/auth/register", email, "recruiter", map[string]any{"password": pw}); code != 409 {
		t.Fatalf("second register = %d, want 409", code)
	}

	// Right password: the account comes back with its role, and never the hash.
	code, out = roleCall(t, srv.URL, "POST", "/v1/auth/password-login", email, "", map[string]any{"password": pw})
	if code != 200 || !strings.Contains(out, `"role":"recruiter"`) || strings.Contains(out, "$2") {
		t.Fatalf("login = %d %s", code, out)
	}
	// No token at all is refused; a wrong password and an unknown email get the same answer.
	if code, _ := roleCall(t, srv.URL, "POST", "/v1/auth/password-login", "", "", map[string]any{"password": pw}); code != 401 {
		t.Fatalf("login without a token = %d", code)
	}
	_, wrong := roleCall(t, srv.URL, "POST", "/v1/auth/password-login", email, "", map[string]any{"password": "wrong password!"})
	_, unknown := roleCall(t, srv.URL, "POST", "/v1/auth/password-login", "nobody-"+uuid.NewString()[:8]+"@example.com", "",
		map[string]any{"password": pw})
	if wrong != unknown || !strings.Contains(wrong, "email or password is wrong") {
		t.Fatalf("wrong = %s, unknown = %s", wrong, unknown)
	}
	// An unknown email never creates an account.
	var n int
	_ = pool.QueryRow(context.Background(), `SELECT count(*) FROM users WHERE email LIKE 'nobody-%@example.com'`).Scan(&n)
	if n != 0 {
		t.Fatalf("a failed login created %d accounts", n)
	}
}

func TestPasswordLoginIsRateLimited(t *testing.T) {
	srv, _, _ := setupProgress(t)
	email := "pw-rate-" + uuid.NewString()[:8] + "@example.com"
	roleCall(t, srv.URL, "POST", "/v1/auth/register", email, "organizer", map[string]any{"password": "a fine password"})
	for i := 0; i < 5; i++ {
		if code, _ := roleCall(t, srv.URL, "POST", "/v1/auth/password-login", email, "", map[string]any{"password": "nope nope nope"}); code != 401 {
			t.Fatalf("try %d = %d, want 401", i+1, code)
		}
	}
	// Even the right password is refused once the email has had 5 failures.
	if code, _ := roleCall(t, srv.URL, "POST", "/v1/auth/password-login", email, "", map[string]any{"password": "a fine password"}); code != 429 {
		t.Fatalf("after 5 failures = %d, want 429", code)
	}
}
