// Package auth checks who is calling the API and whether they own what they ask for.
//
// Hand-off with the website: the Next.js server signs a short-lived HS256 token with AUTH_SECRET
// after Auth.js has logged the person in. The token carries the person's email (and name).
// The API checks the signature, finds or creates the user row, and puts the user id in the request.
//
// Each account has one role, recruiter or organizer. The token also carries the role of the sign-in
// door the person used. The first sign-in sets the account's role; after that, a token for the other
// role is refused.
package auth

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type ctxKey struct{}

// The two roles an account can have.
const (
	RoleRecruiter = "recruiter"
	RoleOrganizer = "organizer"
)

func validRole(role string) bool {
	return role == "" || role == RoleRecruiter || role == RoleOrganizer
}

// Identity is the signed-in person. Role is empty for an account that has not chosen one yet.
type Identity struct {
	UserID string
	Email  string
	Role   string
}

type tokenClaims struct {
	Email string `json:"email"`
	Name  string `json:"name"`
	Role  string `json:"role,omitempty"`
	jwt.RegisteredClaims
}

// Verify checks a token's signature and expiry and returns the email and name inside it.
func Verify(secret, token string) (email, name string, err error) {
	email, name, _, err = VerifyWithRole(secret, token)
	return email, name, err
}

// VerifyWithRole is Verify that also returns the role in the token ("" when it has none).
func VerifyWithRole(secret, token string) (email, name, role string, err error) {
	var claims tokenClaims
	parsed, err := jwt.ParseWithClaims(token, &claims, func(t *jwt.Token) (any, error) {
		return []byte(secret), nil
	}, jwt.WithValidMethods([]string{"HS256"}), jwt.WithExpirationRequired())
	if err != nil || !parsed.Valid {
		return "", "", "", fmt.Errorf("invalid token: %w", err)
	}
	email = strings.ToLower(strings.TrimSpace(claims.Email))
	if email == "" {
		return "", "", "", errors.New("token has no email")
	}
	if !validRole(claims.Role) {
		return "", "", "", errors.New("token has an unknown role")
	}
	return email, claims.Name, claims.Role, nil
}

// Sign makes a token the way the website does. Used by tests and the dev tools.
func Sign(secret, email, name string, ttl time.Duration) (string, error) {
	return SignWithRole(secret, email, name, "", ttl)
}

// SignWithRole is Sign with the role of the sign-in door.
func SignWithRole(secret, email, name, role string, ttl time.Duration) (string, error) {
	claims := tokenClaims{
		Email: email,
		Name:  name,
		Role:  role,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(ttl)),
		},
	}
	return jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(secret))
}

// Middleware requires a valid token on every request that passes through it.
func Middleware(pool *pgxpool.Pool, secret string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			header := r.Header.Get("Authorization")
			token, ok := strings.CutPrefix(header, "Bearer ")
			if !ok || token == "" {
				http.Error(w, `{"error":"sign in required"}`, http.StatusUnauthorized)
				return
			}
			email, name, role, err := VerifyWithRole(secret, token)
			if err != nil {
				http.Error(w, `{"error":"sign in required"}`, http.StatusUnauthorized)
				return
			}
			id, stored, err := upsertUser(r.Context(), pool, email, name, role)
			if err != nil {
				http.Error(w, `{"error":"could not load your account"}`, http.StatusInternalServerError)
				return
			}
			if role != "" && stored != role {
				http.Error(w, `{"error":"this email already has a `+stored+` account"}`, http.StatusForbidden)
				return
			}
			ctx := context.WithValue(r.Context(), ctxKey{}, Identity{UserID: id, Email: email, Role: stored})
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// RequireRole lets a request through only if the account has that role. An account that has not
// chosen a role yet (older accounts, dev tools) is let through.
func RequireRole(role string, next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if id, ok := From(r.Context()); ok && id.Role != "" && id.Role != role {
			http.Error(w, `{"error":"this page is for `+role+` accounts"}`, http.StatusForbidden)
			return
		}
		next(w, r)
	}
}

// From returns the signed-in person for a request that went through Middleware.
func From(ctx context.Context) (Identity, bool) {
	id, ok := ctx.Value(ctxKey{}).(Identity)
	return id, ok
}

// upsertUser finds or creates the user. The role is set by the first sign-in that has one and then
// never changes. It returns the id and the stored role ("" when none).
func upsertUser(ctx context.Context, pool *pgxpool.Pool, email, name, role string) (id, stored string, err error) {
	err = pool.QueryRow(ctx, `
		INSERT INTO users (email, name, role) VALUES ($1, NULLIF($2, ''), NULLIF($3, ''))
		ON CONFLICT (email) DO UPDATE SET
			name = COALESCE(EXCLUDED.name, users.name),
			role = COALESCE(users.role, EXCLUDED.role)
		RETURNING id::text, COALESCE(role, '')`, email, name, role).Scan(&id, &stored)
	return id, stored, err
}
