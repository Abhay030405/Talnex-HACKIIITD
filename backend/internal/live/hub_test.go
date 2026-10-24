package live

import (
	"testing"
)

func TestAnEventReachesOnlyTheStreamsThatWantItsSubject(t *testing.T) {
	h := NewHub(nil, nil)
	a := h.Subscribe(func(id string) bool { return id == "p1" })
	all := h.Subscribe(nil)
	h.Publish([]byte(`{"v":1,"kind":"verdict","subject":{"kind":"project","id":"p1"},"data":{}}`))
	h.Publish([]byte(`{"v":1,"kind":"verdict","subject":{"kind":"project","id":"p2"},"data":{}}`))
	h.Publish([]byte(`not json`))
	if got := len(a.C); got != 1 {
		t.Fatalf("the p1 stream got %d events, want 1", got)
	}
	if got := len(all.C); got != 2 {
		t.Fatalf("the open stream got %d events, want 2", got)
	}
	if ev := <-a.C; ev.Kind != "verdict" || ev.SubjectID != "p1" {
		t.Fatalf("got %+v", ev)
	}
}

func TestASlowViewerMissesEventsInsteadOfBlocking(t *testing.T) {
	h := NewHub(nil, nil)
	slow := h.Subscribe(nil)
	for i := 0; i < cap(slow.C)+50; i++ {
		h.Publish([]byte(`{"kind":"reason","subject":{"id":"p1"}}`))
	}
	if len(slow.C) != cap(slow.C) {
		t.Fatalf("buffer holds %d, want it full at %d", len(slow.C), cap(slow.C))
	}
	h.Unsubscribe(slow)
	h.Unsubscribe(slow) // twice is fine
	if _, open := <-drain(slow.C); open {
		t.Fatal("the stream should be closed after unsubscribing")
	}
}

func drain(c chan Event) chan Event {
	for len(c) > 0 {
		<-c
	}
	return c
}

func TestParseNeedsAKindAndASubject(t *testing.T) {
	if _, ok := Parse([]byte(`{"kind":"x"}`)); ok {
		t.Fatal("an event without a subject must be refused")
	}
	if ev, ok := Parse([]byte(`{"kind":"x","subject":{"id":"s"}}`)); !ok || ev.SubjectID != "s" {
		t.Fatalf("got %+v %v", ev, ok)
	}
}
