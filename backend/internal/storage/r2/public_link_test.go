package r2

import (
	"context"
	"net/url"
	"testing"
	"time"
)

// A view link must point at the address a browser can reach, not the address used inside Docker.
// Making the link needs no network call, so this test needs no running storage.
func TestViewLinkUsesThePublicAddress(t *testing.T) {
	s, err := New(Options{
		Endpoint: "http://s3:9000", PublicEndpoint: "http://localhost:9000", Region: "auto", Bucket: "talnex",
		AccessKey: "a", SecretKey: "b", ViewLinkTTL: time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	link, err := s.ViewLink(context.Background(), "screens/p/r/1")
	if err != nil {
		t.Fatal(err)
	}
	u, _ := url.Parse(link)
	if u.Host != "localhost:9000" || u.Query().Get("X-Amz-Signature") == "" {
		t.Errorf("link = %s", link)
	}
}

func TestViewLinkFallsBackToTheNormalAddress(t *testing.T) {
	s, err := New(Options{Endpoint: "http://s3:9000", Region: "auto", Bucket: "talnex", AccessKey: "a", SecretKey: "b", ViewLinkTTL: time.Minute})
	if err != nil {
		t.Fatal(err)
	}
	link, _ := s.ViewLink(context.Background(), "k")
	if u, _ := url.Parse(link); u.Host != "s3:9000" {
		t.Errorf("link = %s", link)
	}
}

func TestABadPublicAddressIsRefused(t *testing.T) {
	if _, err := New(Options{Endpoint: "http://s3:9000", PublicEndpoint: "not a url", Region: "auto", Bucket: "b", AccessKey: "a", SecretKey: "b"}); err == nil {
		t.Error("want an error for a public address that is not a full address")
	}
}
