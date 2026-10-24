// Package cleanup removes data we must not keep.
package cleanup

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// PurgeOldSMS deletes text messages received by the team phone that are older than the given age.
// Messages are personal data and are only needed for a minute or two. Safe to run any number of times.
func PurgeOldSMS(ctx context.Context, pool *pgxpool.Pool, olderThan time.Duration) (int64, error) {
	tag, err := pool.Exec(ctx, `DELETE FROM inbound_sms WHERE created_at < now() - make_interval(secs => $1)`, olderThan.Seconds())
	if err != nil {
		return 0, fmt.Errorf("purge old text messages: %w", err)
	}
	return tag.RowsAffected(), nil
}
