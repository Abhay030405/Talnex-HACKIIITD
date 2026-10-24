package auth

import (
	"testing"
	"time"
)

const testSecret = "0123456789abcdef0123"

func TestSignAndVerify(t *testing.T) {
	tok, err := Sign(testSecret, "Person@Example.com", "Person", time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	email, name, err := Verify(testSecret, tok)
	if err != nil {
		t.Fatal(err)
	}
	if email != "person@example.com" || name != "Person" {
		t.Fatalf("got %q %q", email, name)
	}
}

func TestVerifyRejectsWrongSecret(t *testing.T) {
	tok, _ := Sign(testSecret, "a@b.com", "", time.Minute)
	if _, _, err := Verify("another-secret-that-is-long", tok); err == nil {
		t.Fatal("expected a signature error")
	}
}

func TestVerifyRejectsExpired(t *testing.T) {
	tok, _ := Sign(testSecret, "a@b.com", "", -10*time.Second)
	if _, _, err := Verify(testSecret, tok); err == nil {
		t.Fatal("expected an expiry error")
	}
}

func TestVerifyRejectsGarbage(t *testing.T) {
	if _, _, err := Verify(testSecret, "not-a-token"); err == nil {
		t.Fatal("expected an error")
	}
}

func TestRoleTravelsInTheToken(t *testing.T) {
	for _, role := range []string{"", RoleRecruiter, RoleOrganizer} {
		tok, err := SignWithRole(testSecret, "a@b.com", "A", role, time.Minute)
		if err != nil {
			t.Fatal(err)
		}
		_, _, got, err := VerifyWithRole(testSecret, tok)
		if err != nil || got != role {
			t.Fatalf("role %q: got %q, %v", role, got, err)
		}
	}
}

func TestVerifyRejectsUnknownRole(t *testing.T) {
	tok, _ := SignWithRole(testSecret, "a@b.com", "", "admin", time.Minute)
	if _, _, _, err := VerifyWithRole(testSecret, tok); err == nil {
		t.Fatal("expected an unknown-role error")
	}
}
