// Package live passes the Python worker's live events (docs/live_events.md) to the people watching.
//
// One dedicated database connection per API process runs LISTEN live; every message is handed to the open
// streams that want its subject. Go and Python still never call each other: the events travel on Postgres's
// own message channel. A viewer that reads too slowly misses events rather than slowing anyone else down.
package live

import (
	"context"
	"encoding/json"
	"log/slog"
	"sync"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Channel is the Postgres notification channel the Python worker sends on.
const Channel = "live"

// Event is one message: its kind, the subject it is about, and the raw JSON as sent.
type Event struct {
	Kind      string
	SubjectID string
	Raw       []byte
}

// Parse reads the kind and subject id out of a message. A message that is not an event gives ok=false.
func Parse(raw []byte) (Event, bool) {
	var head struct {
		Kind    string `json:"kind"`
		Subject struct {
			ID string `json:"id"`
		} `json:"subject"`
	}
	if err := json.Unmarshal(raw, &head); err != nil || head.Kind == "" || head.Subject.ID == "" {
		return Event{}, false
	}
	return Event{Kind: head.Kind, SubjectID: head.Subject.ID, Raw: raw}, true
}

// Sub is one open stream. Events arrive on C; it is closed by Unsubscribe.
type Sub struct {
	C     chan Event
	wants func(subjectID string) bool
}

// Hub fans events out to subscribers.
type Hub struct {
	pool *pgxpool.Pool
	log  *slog.Logger

	mu   sync.Mutex
	subs map[*Sub]struct{}
}

// NewHub makes a hub. Call Run to start listening.
func NewHub(pool *pgxpool.Pool, log *slog.Logger) *Hub {
	if log == nil {
		log = slog.Default()
	}
	return &Hub{pool: pool, log: log, subs: map[*Sub]struct{}{}}
}

// Subscribe opens a stream for the subjects wants accepts (nil means every subject).
func (h *Hub) Subscribe(wants func(subjectID string) bool) *Sub {
	if wants == nil {
		wants = func(string) bool { return true }
	}
	s := &Sub{C: make(chan Event, 256), wants: wants}
	h.mu.Lock()
	h.subs[s] = struct{}{}
	h.mu.Unlock()
	return s
}

// Unsubscribe closes a stream.
func (h *Hub) Unsubscribe(s *Sub) {
	h.mu.Lock()
	if _, ok := h.subs[s]; ok {
		delete(h.subs, s)
		close(s.C)
	}
	h.mu.Unlock()
}

// Publish hands one message to every stream that wants its subject, never waiting on a slow one.
func (h *Hub) Publish(raw []byte) {
	ev, ok := Parse(raw)
	if !ok {
		return
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	for s := range h.subs {
		if !s.wants(ev.SubjectID) {
			continue
		}
		select {
		case s.C <- ev:
		default: // this viewer is behind; it misses this event instead of holding up the others
		}
	}
}

// Run listens until ctx ends, reconnecting after a lost connection.
func (h *Hub) Run(ctx context.Context) {
	for ctx.Err() == nil {
		if err := h.listen(ctx); err != nil && ctx.Err() == nil {
			h.log.Warn("live events: listening stopped, trying again", "err", err)
			select {
			case <-ctx.Done():
			case <-time.After(2 * time.Second):
			}
		}
	}
}

func (h *Hub) listen(ctx context.Context) error {
	pooled, err := h.pool.Acquire(ctx)
	if err != nil {
		return err
	}
	// Taken out of the pool for good: a listening connection must never be handed to anyone else.
	conn := pooled.Hijack()
	defer conn.Close(context.Background())
	if _, err := conn.Exec(ctx, "LISTEN "+Channel); err != nil {
		return err
	}
	h.log.Info("live events: listening")
	for {
		n, err := conn.WaitForNotification(ctx)
		if err != nil {
			return err
		}
		h.Publish([]byte(n.Payload))
	}
}
