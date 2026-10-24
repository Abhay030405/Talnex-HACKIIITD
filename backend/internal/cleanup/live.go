package cleanup

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// LiveEventsKeepFor is how long saved live events stay. They are a viewing aid; the real results stay elsewhere.
const LiveEventsKeepFor = 7 * 24 * time.Hour

// PurgeOldLiveEvents deletes saved live events older than the given age. Safe to run any number of times.
func PurgeOldLiveEvents(ctx context.Context, pool *pgxpool.Pool, olderThan time.Duration) (int64, error) {
	tag, err := pool.Exec(ctx, `DELETE FROM live_events WHERE created_at < now() - make_interval(secs => $1)`, olderThan.Seconds())
	if err != nil {
		return 0, fmt.Errorf("purge old live events: %w", err)
	}
	return tag.RowsAffected(), nil
}
