package github

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// BlameRange is a run of lines in a file that one commit last changed.
type BlameRange struct {
	Start int    `json:"start"`
	End   int    `json:"end"`
	SHA   string `json:"sha"`
}

// graphQLURL is the GraphQL address that goes with the REST address: api.github.com/graphql, or /api/graphql on a
// GitHub Enterprise server whose REST address ends in /api/v3.
func (c *Client) graphQLURL() string {
	if strings.HasSuffix(c.BaseURL, "/api/v3") {
		return strings.TrimSuffix(c.BaseURL, "/v3") + "/graphql"
	}
	return c.BaseURL + "/graphql"
}

// graphQL sends one query. GitHub answers 200 even for a missing repository; those answers come back as ErrNotFound.
func (c *Client) graphQL(ctx context.Context, query string, vars map[string]any, out any) error {
	payload, err := json.Marshal(map[string]any{"query": query, "variables": vars})
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.graphQLURL(), bytes.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return fmt.Errorf("GitHub request: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	switch {
	case resp.StatusCode == http.StatusTooManyRequests ||
		(resp.StatusCode == http.StatusForbidden && resp.Header.Get("X-RateLimit-Remaining") == "0"):
		return ErrRateLimited
	case resp.StatusCode != http.StatusOK:
		return fmt.Errorf("GitHub answered %d for a GraphQL query", resp.StatusCode)
	}
	var envelope struct {
		Data   json.RawMessage `json:"data"`
		Errors []struct {
			Type    string `json:"type"`
			Message string `json:"message"`
		} `json:"errors"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil {
		return fmt.Errorf("read GitHub answer: %w", err)
	}
	for _, e := range envelope.Errors {
		switch {
		case e.Type == "RATE_LIMITED":
			return ErrRateLimited
		case e.Type == "NOT_FOUND" || strings.Contains(strings.ToLower(e.Message), "could not resolve"):
			return ErrNotFound
		}
	}
	if len(envelope.Errors) > 0 {
		return fmt.Errorf("GitHub GraphQL error: %s", envelope.Errors[0].Message)
	}
	if err := json.Unmarshal(envelope.Data, out); err != nil {
		return fmt.Errorf("read GitHub answer: %w", err)
	}
	return nil
}

const blameQuery = `query($owner: String!, $name: String!, $sha: GitObjectID!, $path: String!) {
  repository(owner: $owner, name: $name) {
    object(oid: $sha) {
      ... on Commit {
        blame(path: $path) { ranges { startingLine endingLine commit { oid } } }
      }
    }
  }
}`

// Blame returns, for one file as of one commit, which commit last changed each run of lines. A missing repository,
// commit or file is ErrNotFound. The answer never changes for a commit, so it is cached.
func (c *Client) Blame(ctx context.Context, owner, name, sha, path string) ([]BlameRange, error) {
	key := "blame:" + owner + "/" + name + "@" + sha + ":" + path
	if v, ok := c.cached(key); ok {
		return v.([]BlameRange), nil
	}
	var data struct {
		Repository *struct {
			Object *struct {
				Blame *struct {
					Ranges []struct {
						StartingLine int `json:"startingLine"`
						EndingLine   int `json:"endingLine"`
						Commit       struct {
							OID string `json:"oid"`
						} `json:"commit"`
					} `json:"ranges"`
				} `json:"blame"`
			} `json:"object"`
		} `json:"repository"`
	}
	vars := map[string]any{"owner": owner, "name": name, "sha": sha, "path": path}
	if err := c.graphQL(ctx, blameQuery, vars, &data); err != nil {
		return nil, err
	}
	if data.Repository == nil || data.Repository.Object == nil || data.Repository.Object.Blame == nil {
		return nil, ErrNotFound
	}
	out := make([]BlameRange, 0, len(data.Repository.Object.Blame.Ranges))
	for _, r := range data.Repository.Object.Blame.Ranges {
		out = append(out, BlameRange{Start: r.StartingLine, End: r.EndingLine, SHA: r.Commit.OID})
	}
	c.remember(key, out)
	return out, nil
}

const commitCountQuery = `query($owner: String!, $name: String!, $sha: GitObjectID!) {
  repository(owner: $owner, name: $name) {
    object(oid: $sha) { ... on Commit { history(first: 0) { totalCount } } }
  }
}`

// CommitCount returns how many commits lead up to a commit (its whole history, merges included).
func (c *Client) CommitCount(ctx context.Context, owner, name, sha string) (int, error) {
	key := "count:" + owner + "/" + name + "@" + sha
	if v, ok := c.cached(key); ok {
		return v.(int), nil
	}
	var data struct {
		Repository *struct {
			Object *struct {
				History *struct {
					TotalCount int `json:"totalCount"`
				} `json:"history"`
			} `json:"object"`
		} `json:"repository"`
	}
	if err := c.graphQL(ctx, commitCountQuery, map[string]any{"owner": owner, "name": name, "sha": sha}, &data); err != nil {
		return 0, err
	}
	if data.Repository == nil || data.Repository.Object == nil || data.Repository.Object.History == nil {
		return 0, ErrNotFound
	}
	n := data.Repository.Object.History.TotalCount
	c.remember(key, n)
	return n, nil
}
