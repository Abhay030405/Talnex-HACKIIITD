// Package github reads public facts about a repository from GitHub's official API:
// when it was created and last pushed, its languages, its files and its dependency files.
// It never reads file contents and never writes anything.
package github

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

var (
	// ErrNotFound means the repository does not exist or is private to us.
	ErrNotFound = errors.New("repository not found or private")
	// ErrRateLimited means GitHub asked us to wait; the job queue retries later.
	ErrRateLimited = errors.New("GitHub rate limit reached")
)

// Client talks to the GitHub REST API.
type Client struct {
	HTTP    *http.Client
	BaseURL string
	Token   string
}

// NewClient builds a client. baseURL is the API address from the settings.
func NewClient(baseURL, token string) *Client {
	return &Client{HTTP: &http.Client{Timeout: 20 * time.Second}, BaseURL: strings.TrimRight(baseURL, "/"), Token: token}
}

// Repo is the part of a repository's record we use.
type Repo struct {
	FullName      string    `json:"full_name"`
	Private       bool      `json:"private"`
	Fork          bool      `json:"fork"`
	Archived      bool      `json:"archived"`
	CreatedAt     time.Time `json:"created_at"`
	PushedAt      time.Time `json:"pushed_at"`
	DefaultBranch string    `json:"default_branch"`
	Stars         int       `json:"stargazers_count"`
	SizeKB        int       `json:"size"`
	Parent        *struct {
		FullName string `json:"full_name"`
	} `json:"parent"`
}

// TreeEntry is one file or folder in the repository.
type TreeEntry struct {
	Path string `json:"path"`
	Type string `json:"type"` // "blob" (file) or "tree" (folder)
	Size int    `json:"size"`
}

// Tree is the list of files on the default branch.
type Tree struct {
	Entries   []TreeEntry `json:"tree"`
	Truncated bool        `json:"truncated"`
}

// ParseRepoURL returns the owner and name from a GitHub repository link, or false when the link is not one.
func ParseRepoURL(raw string) (owner, name string, ok bool) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return "", "", false
	}
	if !strings.Contains(raw, "://") {
		raw = "https://" + raw
	}
	u, err := url.Parse(raw)
	if err != nil {
		return "", "", false
	}
	host := strings.ToLower(strings.TrimPrefix(u.Hostname(), "www."))
	if host != "github.com" {
		return "", "", false
	}
	parts := strings.Split(strings.Trim(u.Path, "/"), "/")
	if len(parts) < 2 || parts[0] == "" || parts[1] == "" {
		return "", "", false
	}
	return parts[0], strings.TrimSuffix(parts[1], ".git"), true
}

func (c *Client) get(ctx context.Context, path string, out any) error {
	_, err := c.getPage(ctx, c.BaseURL+path, out)
	return err
}

// getPage reads one page from a full address and returns the address of the next page ("" when this is the last).
func (c *Client) getPage(ctx context.Context, address string, out any) (string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, address, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return "", fmt.Errorf("GitHub request: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	switch {
	case resp.StatusCode == http.StatusNotFound || resp.StatusCode == http.StatusUnavailableForLegalReasons:
		return "", ErrNotFound
	case resp.StatusCode == http.StatusTooManyRequests ||
		(resp.StatusCode == http.StatusForbidden && resp.Header.Get("X-RateLimit-Remaining") == "0"):
		return "", ErrRateLimited
	case resp.StatusCode == http.StatusConflict: // an empty repository has no files yet
		return "", ErrNotFound
	case resp.StatusCode != http.StatusOK:
		return "", fmt.Errorf("GitHub answered %d for %s", resp.StatusCode, req.URL.Path)
	}
	if err := json.Unmarshal(body, out); err != nil {
		return "", fmt.Errorf("read GitHub answer: %w", err)
	}
	return nextLink(resp.Header.Get("Link")), nil
}

// nextLink picks the rel="next" address out of a Link header.
func nextLink(header string) string {
	for _, part := range strings.Split(header, ",") {
		fields := strings.Split(part, ";")
		if len(fields) < 2 {
			continue
		}
		for _, f := range fields[1:] {
			if strings.TrimSpace(f) == `rel="next"` {
				return strings.Trim(strings.TrimSpace(fields[0]), "<>")
			}
		}
	}
	return ""
}

func (c *Client) Repo(ctx context.Context, owner, name string) (Repo, error) {
	var r Repo
	err := c.get(ctx, "/repos/"+url.PathEscape(owner)+"/"+url.PathEscape(name), &r)
	return r, err
}

// Languages returns bytes of code per language.
func (c *Client) Languages(ctx context.Context, owner, name string) (map[string]int, error) {
	out := map[string]int{}
	err := c.get(ctx, "/repos/"+url.PathEscape(owner)+"/"+url.PathEscape(name)+"/languages", &out)
	return out, err
}

// Files returns the whole file list of a branch in one call.
func (c *Client) Files(ctx context.Context, owner, name, branch string) (Tree, error) {
	var t Tree
	err := c.get(ctx, "/repos/"+url.PathEscape(owner)+"/"+url.PathEscape(name)+"/git/trees/"+url.PathEscape(branch)+"?recursive=1", &t)
	return t, err
}
