package github

import (
	"context"
	"fmt"
	"net/url"
	"time"
)

// User is the part of a GitHub account record we use.
type User struct {
	Login       string    `json:"login"`
	CreatedAt   time.Time `json:"created_at"`
	PublicRepos int       `json:"public_repos"`
	Followers   int       `json:"followers"`
}

// User returns a public account record.
func (c *Client) User(ctx context.Context, login string) (User, error) {
	var u User
	err := c.get(ctx, "/users/"+url.PathEscape(login), &u)
	return u, err
}

// OwnedRepos returns up to max public repositories the account owns, most recently pushed first.
func (c *Client) OwnedRepos(ctx context.Context, login string, max int) ([]Repo, error) {
	var out []Repo
	next := c.BaseURL + "/users/" + url.PathEscape(login) + "/repos?type=owner&sort=pushed&per_page=100"
	for next != "" && len(out) < max {
		var page []Repo
		n, err := c.getPage(ctx, next, &page)
		if err != nil {
			return nil, err
		}
		out = append(out, page...)
		next = c.sameHost(n)
	}
	if len(out) > max {
		out = out[:max]
	}
	return out, nil
}

// AuthorCommits returns up to perPage commits on the default branch made by author since a moment, newest first.
// One page only: it is a sample of recent activity, not the full history.
func (c *Client) AuthorCommits(ctx context.Context, owner, name, author string, since time.Time, perPage int) ([]Commit, error) {
	q := url.Values{}
	q.Set("author", author)
	q.Set("since", since.UTC().Format(time.RFC3339))
	q.Set("per_page", fmt.Sprint(perPage))
	var raw []commitJSON
	if err := c.get(ctx, repoPath(owner, name)+"/commits?"+q.Encode(), &raw); err != nil {
		return nil, err
	}
	out := make([]Commit, 0, len(raw))
	for _, r := range raw {
		out = append(out, Commit{SHA: r.SHA, Date: r.Commit.Committer.Date})
	}
	return out, nil
}

// ExternalPRs counts the pull requests the account opened on repositories it does not own (one search request).
func (c *Client) ExternalPRs(ctx context.Context, login string) (int, error) {
	var out struct {
		TotalCount int `json:"total_count"`
	}
	q := url.QueryEscape("type:pr author:" + login + " -user:" + login)
	err := c.get(ctx, "/search/issues?per_page=1&q="+q, &out)
	return out.TotalCount, err
}
