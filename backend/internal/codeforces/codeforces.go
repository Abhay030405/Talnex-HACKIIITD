// Package codeforces reads public facts about a coder from Codeforces' official API: rating, rank, contests and
// solved problems. It only reads, and it never logs in.
package codeforces

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"slices"
	"sort"
	"strings"
	"time"
)

var (
	// ErrNotFound means Codeforces has no user with this handle.
	ErrNotFound = errors.New("Codeforces handle not found")
	// ErrRateLimited means Codeforces asked us to slow down; the job queue retries later.
	ErrRateLimited = errors.New("Codeforces rate limit reached")
)

// Client talks to the Codeforces API.
type Client struct {
	HTTP    *http.Client
	BaseURL string
}

// NewClient builds a client. baseURL is the API address from the settings.
func NewClient(baseURL string) *Client {
	return &Client{HTTP: &http.Client{Timeout: 30 * time.Second}, BaseURL: strings.TrimRight(baseURL, "/")}
}

// User is the part of a user record we use. Rating fields are zero for someone who never took part in a rated contest.
type User struct {
	Handle        string `json:"handle"`
	Rating        int    `json:"rating"`
	MaxRating     int    `json:"maxRating"`
	Rank          string `json:"rank"`
	MaxRank       string `json:"maxRank"`
	LastOnlineSec int64  `json:"lastOnlineTimeSeconds"`
}

// RatingChange is one rated contest.
type RatingChange struct {
	ContestID   int    `json:"contestId"`
	ContestName string `json:"contestName"`
	OldRating   int    `json:"oldRating"`
	NewRating   int    `json:"newRating"`
	UpdateSec   int64  `json:"ratingUpdateTimeSeconds"`
}

// Submission is one submission.
type Submission struct {
	ContestID  int    `json:"contestId"`
	CreatedSec int64  `json:"creationTimeSeconds"`
	Verdict    string `json:"verdict"`
	Author     struct {
		// CONTESTANT is a real contest entry; PRACTICE, VIRTUAL and OUT_OF_COMPETITION are not.
		ParticipantType string `json:"participantType"`
	} `json:"author"`
	Problem struct {
		ContestID int    `json:"contestId"`
		Index     string `json:"index"`
		Name      string `json:"name"`
	} `json:"problem"`
}

type envelope struct {
	Status  string          `json:"status"`
	Comment string          `json:"comment"`
	Result  json.RawMessage `json:"result"`
}

func (c *Client) get(ctx context.Context, method string, query url.Values, out any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.BaseURL+"/"+method+"?"+query.Encode(), nil)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return fmt.Errorf("codeforces %s: %w", method, err)
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 64<<20))
	if err != nil {
		return fmt.Errorf("codeforces %s: %w", method, err)
	}
	if resp.StatusCode == http.StatusTooManyRequests {
		return ErrRateLimited
	}
	var env envelope
	jsonErr := json.Unmarshal(body, &env)
	// Codeforces answers 400 with a FAILED body for an unknown handle, so read the body before the status code.
	if jsonErr == nil && env.Status == "FAILED" {
		comment := strings.ToLower(env.Comment)
		switch {
		case strings.Contains(comment, "limit exceeded"):
			return ErrRateLimited
		case strings.Contains(comment, "not found"):
			return ErrNotFound
		}
		return fmt.Errorf("codeforces %s: %s", method, env.Comment)
	}
	if resp.StatusCode >= 500 {
		return fmt.Errorf("codeforces %s: status %d", method, resp.StatusCode)
	}
	if jsonErr != nil || env.Status != "OK" {
		return fmt.Errorf("codeforces %s: unexpected answer (status %d)", method, resp.StatusCode)
	}
	return json.Unmarshal(env.Result, out)
}

// User reads the profile of one handle.
func (c *Client) User(ctx context.Context, handle string) (User, error) {
	var users []User
	if err := c.get(ctx, "user.info", url.Values{"handles": {handle}}, &users); err != nil {
		return User{}, err
	}
	if len(users) == 0 {
		return User{}, ErrNotFound
	}
	return users[0], nil
}

// Ratings lists the rated contests of a handle, oldest first.
func (c *Client) Ratings(ctx context.Context, handle string) ([]RatingChange, error) {
	var out []RatingChange
	err := c.get(ctx, "user.rating", url.Values{"handle": {handle}}, &out)
	return out, err
}

// Submissions lists every submission of a handle, newest first.
func (c *Client) Submissions(ctx context.Context, handle string) ([]Submission, error) {
	var out []Submission
	err := c.get(ctx, "user.status", url.Values{"handle": {handle}}, &out)
	return out, err
}

// Signals are the facts TalNex keeps about a Codeforces profile.
type Signals struct {
	Handle         string `json:"handle"`
	Rating         int    `json:"rating"`
	MaxRating      int    `json:"max_rating"`
	Rank           string `json:"rank"`
	MaxRank        string `json:"max_rank"`
	Contests       int    `json:"contests"`
	SolvedProblems int    `json:"solved_problems"`
	// RecentActivity is the date (UTC, YYYY-MM-DD) of the newest submission, or empty when there is none.
	RecentActivity string `json:"recent_activity"`
	// RecentRatings is the rating after each of the last few rated contests, oldest first (for a rating trend).
	RecentRatings []int `json:"recent_ratings"`
	// AllSkipped lists contests where every contest submission was Skipped (architecture section 18).
	AllSkipped []SkippedContest `json:"all_skipped_contests"`
	// PartlySkipped lists single problems that were Skipped in a contest that was not skipped as a whole.
	PartlySkipped []SkippedProblem `json:"partly_skipped"`
}

// Fetch gathers the signals for one handle. ErrNotFound means the handle does not exist.
func (c *Client) Fetch(ctx context.Context, handle string) (Signals, error) {
	user, err := c.User(ctx, handle)
	if err != nil {
		return Signals{}, err
	}
	ratings, err := c.Ratings(ctx, handle)
	if err != nil {
		return Signals{}, err
	}
	subs, err := c.Submissions(ctx, handle)
	if err != nil {
		return Signals{}, err
	}
	out := Summarise(user, ratings, subs)
	now := time.Now()
	out.AllSkipped = FindAllSkipped(ratings, subs, now)
	out.PartlySkipped = FindPartlySkipped(ratings, subs, now)
	return out, nil
}

// Summarise turns the raw answers into the kept facts. A problem counts once, however many accepted tries it has.
// recentRatings is how many of the latest rated contests are kept for the rating trend.
const recentRatings = 6

func Summarise(user User, ratings []RatingChange, subs []Submission) Signals {
	solved := map[string]bool{}
	var newest int64
	for _, s := range subs {
		if s.CreatedSec > newest {
			newest = s.CreatedSec
		}
		if s.Verdict == "OK" {
			solved[fmt.Sprintf("%d%s", s.Problem.ContestID, s.Problem.Index)+"|"+s.Problem.Name] = true
		}
	}
	out := Signals{
		Handle: user.Handle, Rating: user.Rating, MaxRating: user.MaxRating, Rank: user.Rank, MaxRank: user.MaxRank,
		Contests: len(ratings), SolvedProblems: len(solved), RecentRatings: []int{},
	}
	for _, r := range ratings[max(0, len(ratings)-recentRatings):] {
		out.RecentRatings = append(out.RecentRatings, r.NewRating)
	}
	if newest > 0 {
		out.RecentActivity = time.Unix(newest, 0).UTC().Format("2006-01-02")
	}
	return out
}

// Tuning for the "all skipped" check (architecture section 18).
const (
	recentContestsChecked = 5                  // the last few rated contests are looked at
	suddenJump            = 200                // a rating rise this big also puts a contest on the list
	settleTime            = 3 * 24 * time.Hour // very recent contests are left alone until the site's own checks settle
	minSkipped            = 2                  // a single Skipped submission is normal (a resubmission) and ignored
)

// SkippedContest is a contest where all of the person's contest submissions were Skipped.
type SkippedContest struct {
	ContestID   int    `json:"contest_id"`
	ContestName string `json:"contest_name"`
	Submissions int    `json:"submissions"`
}

// FindAllSkipped looks at the last few rated contests, plus any with a sudden rating jump, and returns those where
// every contest submission is Skipped. Practice, virtual and out-of-competition submissions are removed first, a single
// Skipped submission is ignored, and contests that ended in the last few days are not judged yet.
func FindAllSkipped(ratings []RatingChange, subs []Submission, now time.Time) []SkippedContest {
	if len(ratings) == 0 {
		return nil
	}
	ordered := append([]RatingChange(nil), ratings...)
	sort.Slice(ordered, func(i, j int) bool { return ordered[i].UpdateSec < ordered[j].UpdateSec })

	chosen := map[int]RatingChange{}
	for i, r := range ordered {
		if i >= len(ordered)-recentContestsChecked || r.NewRating-r.OldRating >= suddenJump {
			chosen[r.ContestID] = r
		}
	}

	type tally struct{ all, skipped int }
	counts := map[int]*tally{}
	for _, sub := range subs {
		if sub.Author.ParticipantType != "CONTESTANT" {
			continue
		}
		if _, ok := chosen[sub.ContestID]; !ok {
			continue
		}
		t := counts[sub.ContestID]
		if t == nil {
			t = &tally{}
			counts[sub.ContestID] = t
		}
		t.all++
		if sub.Verdict == "SKIPPED" {
			t.skipped++
		}
	}

	var out []SkippedContest
	for _, r := range ordered {
		c, ok := chosen[r.ContestID]
		t := counts[r.ContestID]
		if !ok || t == nil || t.skipped != t.all || t.all < minSkipped {
			continue
		}
		if now.Sub(time.Unix(c.UpdateSec, 0)) < settleTime {
			continue
		}
		out = append(out, SkippedContest{ContestID: c.ContestID, ContestName: c.ContestName, Submissions: t.all})
	}
	return out
}

// SkippedProblem is one problem whose contest submissions were Skipped while the rest of the contest was judged.
// Codeforces gives no reason for a Skip. Resubmitted means a later submission of the same problem exists, which is the
// usual innocent cause (only the last try is judged); without one, the skip has no innocent explanation in the data.
type SkippedProblem struct {
	ContestID   int    `json:"contest_id"`
	ContestName string `json:"contest_name"`
	Problem     string `json:"problem"`
	Skipped     int    `json:"skipped"`
	Resubmitted bool   `json:"resubmitted"`
}

// FindPartlySkipped looks at every rated contest and returns each problem with a Skipped contest submission, in a
// contest that was not skipped as a whole (FindAllSkipped covers those). Only real contest entries count, and contests
// that ended in the last few days are left alone until the site's own checks settle.
func FindPartlySkipped(ratings []RatingChange, subs []Submission, now time.Time) []SkippedProblem {
	rated := map[int]RatingChange{}
	for _, r := range ratings {
		if now.Sub(time.Unix(r.UpdateSec, 0)) >= settleTime {
			rated[r.ContestID] = r
		}
	}
	type key struct {
		contest int
		problem string
	}
	entries := map[int][]Submission{}
	for _, s := range subs {
		if _, ok := rated[s.ContestID]; ok && s.Author.ParticipantType == "CONTESTANT" {
			entries[s.ContestID] = append(entries[s.ContestID], s)
		}
	}
	var out []SkippedProblem
	for _, r := range ratings {
		ss, ok := entries[r.ContestID]
		if !ok {
			continue
		}
		skipped, judged := map[key][]int64{}, false
		for _, s := range ss {
			if s.Verdict == "SKIPPED" {
				k := key{r.ContestID, s.Problem.Index}
				skipped[k] = append(skipped[k], s.CreatedSec)
			} else {
				judged = true
			}
		}
		if !judged || len(skipped) == 0 {
			continue // nothing skipped, or the whole contest was (FindAllSkipped)
		}
		idx := make([]string, 0, len(skipped))
		for k := range skipped {
			idx = append(idx, k.problem)
		}
		sort.Strings(idx)
		for _, p := range idx {
			times := skipped[key{r.ContestID, p}]
			last := slices.Max(times)
			later := slices.ContainsFunc(ss, func(s Submission) bool {
				return s.Problem.Index == p && s.Verdict != "SKIPPED" && s.CreatedSec > last
			})
			out = append(out, SkippedProblem{ContestID: r.ContestID, ContestName: r.ContestName, Problem: p,
				Skipped: len(times), Resubmitted: later})
		}
	}
	return out
}
