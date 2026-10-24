package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"sort"
	"time"

	"github.com/jackc/pgx/v5"
)

// getProjectProof returns the proof card of one hackathon project (built by the `project_report` stage). The event owner only; a
// stranger gets "not found". Like the recruiter report, every step's `proof_key` is replaced by a short-lived `proof_url`, so raw
// storage keys never leave the server.
func (s *server) getProjectProof(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedProject(w, r)
	if !ok {
		return
	}
	var raw []byte
	var hasGaps bool
	var generatedAt time.Time
	err := s.opts.Pool.QueryRow(r.Context(),
		`SELECT report, has_gaps, generated_at FROM project_reports WHERE project_id = $1::uuid`, id).Scan(&raw, &hasGaps, &generatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "the proof card is not ready yet")
		return
	}
	if err != nil {
		s.fail(w, "read proof card", err)
		return
	}
	var card map[string]any
	if err := json.Unmarshal(raw, &card); err != nil {
		s.fail(w, "decode proof card", err)
		return
	}
	card["has_gaps"] = hasGaps
	card["generated_at"] = generatedAt.UTC().Format(time.RFC3339)
	// swapProofKeys walks projects[].features[].proof[], so the card is handed to it in that shape and taken back out.
	wrapped := map[string]any{"projects": []any{card}}
	s.swapProofKeys(r.Context(), wrapped)
	s.swapOpinionKeys(r.Context(), card)
	writeJSON(w, http.StatusOK, card)
}

// viewLinkInto replaces holder[keyName] (a storage key) with holder[urlName] (a short-lived link). The key is always removed.
func (s *server) viewLinkInto(ctx context.Context, holder map[string]any, keyName, urlName string) {
	key, _ := holder[keyName].(string)
	delete(holder, keyName)
	if key == "" || s.opts.ProofLinks == nil {
		return
	}
	link, err := s.opts.ProofLinks.ViewLink(ctx, key)
	if err != nil {
		s.opts.Log.Error("make proof link", "err", err)
		return
	}
	holder[urlName] = link
}

// swapOpinionKeys turns the screenshot key of every AI opinion part into a short-lived link.
func (s *server) swapOpinionKeys(ctx context.Context, card map[string]any) {
	opinion, _ := card["ai_opinion"].(map[string]any)
	for _, kind := range []string{"ui", "innovation"} {
		box, _ := opinion[kind].(map[string]any)
		parts, _ := box["parts"].([]any)
		for _, p := range parts {
			if part, _ := p.(map[string]any); part != nil {
				s.viewLinkInto(ctx, part, "proof_key", "proof_url")
			}
		}
	}
}

// getEventCompare is the organizer's comparison data for a whole event: "these teams built this feature best" (top 3 per feature,
// never one winner), the best Access / Core / Logic / Reliability for open-theme events, and the pairs of teams whose code has the
// same shape. Every screenshot key becomes a short-lived link. Nothing here ranks the teams or picks a winner.
func (s *server) getEventCompare(w http.ResponseWriter, r *http.Request) {
	_, eventID, ok := s.ownedEvent(w, r)
	if !ok {
		return
	}
	var ready bool
	if err := s.opts.Pool.QueryRow(r.Context(), `SELECT EXISTS (SELECT 1 FROM jobs WHERE pipeline = 'hackathon_event' AND job_type = 'ai_opinion'
		AND target_type = 'event' AND target_id = $1::uuid AND status = 'done')`, eventID).Scan(&ready); err != nil {
		s.fail(w, "read event checks", err)
		return
	}
	rows, err := s.opts.Pool.Query(r.Context(), `SELECT kind, feature_name, best_teams FROM feature_groups WHERE event_id = $1::uuid ORDER BY kind, feature_name`, eventID)
	if err != nil {
		s.fail(w, "read feature groups", err)
		return
	}
	defer rows.Close()
	features, groupBests := []map[string]any{}, []map[string]any{}
	for rows.Next() {
		var kind, name string
		var raw []byte
		if err := rows.Scan(&kind, &name, &raw); err != nil {
			s.fail(w, "read feature groups", err)
			return
		}
		var best []map[string]any
		if err := json.Unmarshal(raw, &best); err != nil {
			s.fail(w, "decode feature group", err)
			return
		}
		for _, b := range best {
			keys, _ := b["proof_keys"].([]any)
			delete(b, "proof_keys")
			urls := []string{}
			for _, k := range keys {
				if key, _ := k.(string); key != "" && s.opts.ProofLinks != nil {
					if link, err := s.opts.ProofLinks.ViewLink(r.Context(), key); err == nil {
						urls = append(urls, link)
					}
				}
			}
			b["proof_urls"] = urls
		}
		entry := map[string]any{"name": name, "best_teams": best}
		if kind == "group" {
			groupBests = append(groupBests, entry)
		} else {
			features = append(features, entry)
		}
	}
	if err := rows.Err(); err != nil {
		s.fail(w, "read feature groups", err)
		return
	}

	pairRows, err := s.opts.Pool.Query(r.Context(), `
		SELECT a.id::text, a.team_name, b.id::text, b.team_name, c.shared_pct::float8, c.level, c.matching_files
		  FROM copy_pairs c JOIN projects a ON a.id = c.project_a_id JOIN projects b ON b.id = c.project_b_id
		 WHERE c.event_id = $1::uuid ORDER BY c.shared_pct DESC, lower(a.team_name), lower(b.team_name)`, eventID)
	if err != nil {
		s.fail(w, "read copy pairs", err)
		return
	}
	defer pairRows.Close()
	pairs := []map[string]any{}
	for pairRows.Next() {
		var aID, aName, bID, bName string
		var pct float64
		var level *string
		var files []byte
		if err := pairRows.Scan(&aID, &aName, &bID, &bName, &pct, &level, &files); err != nil {
			s.fail(w, "read copy pairs", err)
			return
		}
		var matching any
		_ = json.Unmarshal(files, &matching)
		pairs = append(pairs, map[string]any{"team_a": map[string]any{"id": aID, "name": aName}, "team_b": map[string]any{"id": bID, "name": bName},
			"shared_pct": pct, "level": level, "matching_files": matching})
	}
	if err := pairRows.Err(); err != nil {
		s.fail(w, "read copy pairs", err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"ready": ready, "features": features, "group_bests": groupBests, "copy_pairs": pairs,
		"notes": []string{"Each feature lists up to three teams that built it best, in no ranking between features and never one winner.",
			"A copy pair is a reason for a person to look; TalNex cannot tell who wrote the code first."},
	})
}

type overviewGroup struct {
	Group       string   `json:"group"`
	Score       *float64 `json:"score"`
	Coverage    float64  `json:"coverage"`
	LowCoverage bool     `json:"low_coverage"`
}

type overviewProject struct {
	ID            string          `json:"id"`
	TeamName      string          `json:"team_name"`
	Status        string          `json:"status"`
	HasVideo      bool            `json:"has_video"`
	HasLive       bool            `json:"has_live"`
	HasRepo       bool            `json:"has_repo"`
	TalnexScore10 *float64        `json:"talnex_score10"`
	Coverage      *float64        `json:"coverage"`
	WeightedTotal *float64        `json:"weighted_total"`
	Groups        []overviewGroup `json:"groups"`
	Flags         map[string]int  `json:"flags"`
	ReportReady   bool            `json:"report_ready"`
}

// getEventOverview is the organizer's dashboard data: every project of the event with its status, its TalNex score, its group
// scores and how many flags of each level it has. Projects are ordered by team name, never by score: TalNex does not rank teams
// or pick a winner (feature comparison shows "teams that built this best", never one best team).
func (s *server) getEventOverview(w http.ResponseWriter, r *http.Request) {
	who, eventID, ok := s.ownedEvent(w, r)
	if !ok {
		return
	}
	event, err := s.events.Get(r.Context(), who.UserID, eventID)
	if err != nil {
		s.fail(w, "get event", err)
		return
	}
	rows, err := s.opts.Pool.Query(r.Context(), `
		SELECT p.id::text, p.team_name, p.status, p.video_url IS NOT NULL, p.live_url IS NOT NULL, p.repo_url IS NOT NULL,
		       EXISTS (SELECT 1 FROM project_reports pr WHERE pr.project_id = p.id)
		  FROM projects p WHERE p.event_id = $1::uuid ORDER BY lower(p.team_name), p.created_at`, eventID)
	if err != nil {
		s.fail(w, "list projects", err)
		return
	}
	defer rows.Close()
	projects := []*overviewProject{}
	byID := map[string]*overviewProject{}
	for rows.Next() {
		p := &overviewProject{Groups: []overviewGroup{}, Flags: map[string]int{}}
		if err := rows.Scan(&p.ID, &p.TeamName, &p.Status, &p.HasVideo, &p.HasLive, &p.HasRepo, &p.ReportReady); err != nil {
			s.fail(w, "read projects", err)
			return
		}
		projects = append(projects, p)
		byID[p.ID] = p
	}
	if err := rows.Err(); err != nil {
		s.fail(w, "read projects", err)
		return
	}

	scores, err := s.opts.Pool.Query(r.Context(), `
		SELECT s.project_id::text, s.score_group, s.score::float8, s.coverage::float8
		  FROM scores s JOIN projects p ON p.id = s.project_id WHERE p.event_id = $1::uuid`, eventID)
	if err != nil {
		s.fail(w, "read scores", err)
		return
	}
	defer scores.Close()
	for scores.Next() {
		var pid, group string
		var score *float64
		var coverage float64
		if err := scores.Scan(&pid, &group, &score, &coverage); err != nil {
			s.fail(w, "read scores", err)
			return
		}
		p := byID[pid]
		switch {
		case p == nil:
		case group == "talnex":
			if score != nil {
				v := *score / 10
				p.TalnexScore10 = &v
			}
			p.Coverage = &coverage
		case group == "weighted_total":
			p.WeightedTotal = score
		default:
			p.Groups = append(p.Groups, overviewGroup{Group: group, Score: score, Coverage: coverage, LowCoverage: coverage < 50})
		}
	}
	if err := scores.Err(); err != nil {
		s.fail(w, "read scores", err)
		return
	}
	for _, p := range projects {
		sort.Slice(p.Groups, func(i, j int) bool { return p.Groups[i].Group < p.Groups[j].Group })
	}

	flags, err := s.opts.Pool.Query(r.Context(), `
		SELECT f.project_id::text, f.level, count(*) FROM flags f JOIN projects p ON p.id = f.project_id
		 WHERE p.event_id = $1::uuid GROUP BY f.project_id, f.level`, eventID)
	if err != nil {
		s.fail(w, "read flags", err)
		return
	}
	defer flags.Close()
	for flags.Next() {
		var pid, level string
		var n int
		if err := flags.Scan(&pid, &level, &n); err != nil {
			s.fail(w, "read flags", err)
			return
		}
		if p := byID[pid]; p != nil {
			p.Flags[level] = n
		}
	}
	if err := flags.Err(); err != nil {
		s.fail(w, "read flags", err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"event": event, "projects": projects})
}
