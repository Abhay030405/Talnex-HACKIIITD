package github

import (
	"context"
	"fmt"
	"net/url"
	"sort"
	"strings"
	"sync"
	"time"
)

// FileCommit is one commit that changed a file, with what we show about it. AuthorLogin is empty when the commit's
// email is tied to no GitHub account ("unlinked author"); the name and email are never kept.
type FileCommit struct {
	SHA          string
	AuthorLogin  string
	IsBot        bool
	CommittedAt  time.Time // the committer date; the author of a commit can set it to anything
	Message      string    // first line only
	Parents      int
	Additions    int
	Deletions    int
	FilesChanged int
}

type fileCommitJSON struct {
	SHA    string `json:"sha"`
	Commit struct {
		Message   string `json:"message"`
		Committer struct {
			Date time.Time `json:"date"`
		} `json:"committer"`
	} `json:"commit"`
	Author *struct {
		Login string `json:"login"`
		Type  string `json:"type"`
	} `json:"author"`
	Parents []struct {
		SHA string `json:"sha"`
	} `json:"parents"`
	Stats *struct {
		Additions int `json:"additions"`
		Deletions int `json:"deletions"`
	} `json:"stats"`
	Files []struct {
		Filename string `json:"filename"`
	} `json:"files"`
}

func (r fileCommitJSON) toCommit() FileCommit {
	c := FileCommit{SHA: r.SHA, CommittedAt: r.Commit.Committer.Date, Parents: len(r.Parents)}
	c.Message, _, _ = strings.Cut(strings.TrimSpace(r.Commit.Message), "\n")
	c.Message = strings.TrimSpace(c.Message)
	if r.Author != nil {
		c.AuthorLogin = r.Author.Login
		c.IsBot = r.Author.Type == "Bot" || IsBotLogin(r.Author.Login)
	}
	if r.Stats != nil {
		c.Additions, c.Deletions = r.Stats.Additions, r.Stats.Deletions
	}
	c.FilesChanged = len(r.Files)
	return c
}

// knownBots are bot accounts that do not end in "[bot]".
var knownBots = map[string]bool{
	"dependabot": true, "dependabot-preview": true, "renovate": true, "renovate-bot": true, "greenkeeper": true,
	"github-actions": true, "snyk-bot": true, "imgbot": true, "allcontributors": true, "pre-commit-ci": true,
	"codecov-io": true, "deepsource-autofix": true, "web-flow": true, "semantic-release-bot": true,
}

// IsBotLogin reports whether a login belongs to a bot (dependabot, github-actions, renovate and similar).
func IsBotLogin(login string) bool {
	l := strings.ToLower(strings.TrimSpace(login))
	return strings.HasSuffix(l, "[bot]") || knownBots[l]
}

// FileCommits returns up to limit commits that changed one file, newest first, as of a commit. Only the list call is
// made here; the line counts come from CommitDetail.
func (c *Client) FileCommits(ctx context.Context, owner, name, sha, path string, limit int) ([]FileCommit, error) {
	key := fmt.Sprintf("filecommits:%s/%s@%s:%s:%d", owner, name, sha, path, limit)
	if v, ok := c.cached(key); ok {
		return v.([]FileCommit), nil
	}
	var out []FileCommit
	q := url.Values{}
	q.Set("sha", sha)
	q.Set("path", path)
	q.Set("per_page", fmt.Sprint(min(limit, 100)))
	next := c.BaseURL + repoPath(owner, name) + "/commits?" + q.Encode()
	for next != "" && len(out) < limit {
		var raw []fileCommitJSON
		n, err := c.getPage(ctx, next, &raw)
		if err != nil {
			return nil, err
		}
		for _, r := range raw {
			if len(out) == limit {
				break
			}
			out = append(out, r.toCommit())
		}
		next = c.sameHost(n)
	}
	c.remember(key, out)
	return out, nil
}

// CommitDetail returns one commit with its line counts and the number of files it changed. A commit never changes,
// so it is cached.
func (c *Client) CommitDetail(ctx context.Context, owner, name, sha string) (FileCommit, error) {
	key := "commit:" + owner + "/" + name + "@" + sha
	if v, ok := c.cached(key); ok {
		return v.(FileCommit), nil
	}
	var raw fileCommitJSON
	if err := c.get(ctx, repoPath(owner, name)+"/commits/"+url.PathEscape(sha), &raw); err != nil {
		return FileCommit{}, err
	}
	out := raw.toCommit()
	c.remember(key, out)
	return out, nil
}

// BranchGraph returns the parents of up to limit commits leading up to a commit, newest first. It is what ties a
// push to the commits it brought in.
func (c *Client) BranchGraph(ctx context.Context, owner, name, sha string, limit int) (map[string][]string, bool, error) {
	key := fmt.Sprintf("graph:%s/%s@%s:%d", owner, name, sha, limit)
	if v, ok := c.cached(key); ok {
		g := v.(graphResult)
		return g.parents, g.complete, nil
	}
	parents := map[string][]string{}
	q := url.Values{}
	q.Set("sha", sha)
	q.Set("per_page", "100")
	next := c.BaseURL + repoPath(owner, name) + "/commits?" + q.Encode()
	for next != "" && len(parents) < limit {
		var raw []fileCommitJSON
		n, err := c.getPage(ctx, next, &raw)
		if err != nil {
			return nil, false, err
		}
		for _, r := range raw {
			ps := make([]string, 0, len(r.Parents))
			for _, p := range r.Parents {
				ps = append(ps, p.SHA)
			}
			parents[r.SHA] = ps
		}
		next = c.sameHost(n)
	}
	complete := next == ""
	c.remember(key, graphResult{parents: parents, complete: complete})
	return parents, complete, nil
}

type graphResult struct {
	parents  map[string][]string
	complete bool
}

// Push is one change of a branch recorded by GitHub itself (the repository activity list): when it happened and the
// commit the branch pointed to afterwards. Unlike commit dates, the author cannot set this time.
type Push struct {
	Before string // where the branch pointed before; empty when the push created it
	After  string
	At     time.Time
}

// Pushes returns GitHub's own record of the changes to a branch, oldest first: pushes, force pushes and merged pull
// requests. It reads at most maxPages pages of 100. A repository without such records gives an empty list.
func (c *Client) Pushes(ctx context.Context, owner, name, branch string, maxPages int) ([]Push, error) {
	q := url.Values{}
	q.Set("ref", branch)
	q.Set("direction", "asc")
	q.Set("per_page", "100")
	next := c.BaseURL + repoPath(owner, name) + "/activity?" + q.Encode()
	var out []Push
	for page := 0; next != "" && page < maxPages; page++ {
		var raw []struct {
			Before       string    `json:"before"`
			After        string    `json:"after"`
			Timestamp    time.Time `json:"timestamp"`
			ActivityType string    `json:"activity_type"`
		}
		n, err := c.getPage(ctx, next, &raw)
		if err != nil {
			return nil, err
		}
		for _, r := range raw {
			if r.ActivityType == "branch_deletion" || r.After == "" || strings.Trim(r.After, "0") == "" {
				continue
			}
			before := r.Before
			if strings.Trim(before, "0") == "" {
				before = ""
			}
			out = append(out, Push{Before: before, After: r.After, At: r.Timestamp})
		}
		next = c.sameHost(n)
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].At.Before(out[j].At) })
	return out, nil
}

// PushTimes gives each commit the time of the first recorded push that made it part of the branch: the push's own
// commit and every earlier commit behind it that no earlier push brought in. Commits the records do not reach are
// left out: a history older than the records (everything behind the first recorded push's starting point), or past
// the graph we read.
func PushTimes(pushes []Push, parents map[string][]string) map[string]time.Time {
	out := map[string]time.Time{}
	older := map[string]bool{}
	if len(pushes) > 0 && pushes[0].Before != "" {
		walk(pushes[0].Before, parents, func(sha string) bool {
			if older[sha] {
				return false
			}
			older[sha] = true
			return true
		})
	}
	for _, p := range pushes {
		walk(p.After, parents, func(sha string) bool {
			if _, done := out[sha]; done || older[sha] {
				return false
			}
			out[sha] = p.At
			return true
		})
	}
	return out
}

// walk visits a commit and the commits behind it that are in the graph. visit returns false to stop going further back.
func walk(start string, parents map[string][]string, visit func(sha string) bool) {
	stack := []string{start}
	for len(stack) > 0 {
		sha := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		ps, known := parents[sha]
		if !known || !visit(sha) {
			continue
		}
		stack = append(stack, ps...)
	}
}

// sameHost keeps a next-page address only when it points at the API we were given, so the token is never sent
// anywhere else.
func (c *Client) sameHost(next string) string {
	if next == "" || !strings.HasPrefix(next, c.BaseURL+"/") {
		return ""
	}
	return next
}

// The history cache keeps answers that never change for a commit (blame, commit details, file and branch history as
// of a commit). It lives in memory for the life of one worker process, shared by every client; the key includes the
// API address, so test servers never mix. It is emptied when it grows past maxCached entries.
const maxCached = 20000

var historyCache = struct {
	sync.Mutex
	items map[string]any
}{items: map[string]any{}}

func (c *Client) cached(key string) (any, bool) {
	historyCache.Lock()
	defer historyCache.Unlock()
	v, ok := historyCache.items[c.BaseURL+"|"+key]
	return v, ok
}

func (c *Client) remember(key string, v any) {
	historyCache.Lock()
	defer historyCache.Unlock()
	if len(historyCache.items) >= maxCached {
		historyCache.items = map[string]any{}
	}
	historyCache.items[c.BaseURL+"|"+key] = v
}
