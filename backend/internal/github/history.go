package github

import (
	"context"
	"encoding/base64"
	"fmt"
	"net/url"
	"strings"
	"time"
)

// Commit is one commit on a branch, with the dates it carries.
type Commit struct {
	SHA  string
	Date time.Time // the committer date; the author of a commit can set it to anything
}

// TreeNode is one file or folder, with the id of its content. Two files with the same id are the same content.
type TreeNode struct {
	Path string `json:"path"`
	Type string `json:"type"` // "blob" (file) or "tree" (folder)
	SHA  string `json:"sha"`
	Size int    `json:"size"`
}

// SnapshotTree is the full file list as of one commit.
type SnapshotTree struct {
	Nodes     []TreeNode `json:"tree"`
	Truncated bool       `json:"truncated"`
}

type commitJSON struct {
	SHA    string `json:"sha"`
	Commit struct {
		Committer struct {
			Date time.Time `json:"date"`
		} `json:"committer"`
	} `json:"commit"`
}

func repoPath(owner, name string) string {
	return "/repos/" + url.PathEscape(owner) + "/" + url.PathEscape(name)
}

// Commits returns up to perPage commits of a branch, newest first. When until is not zero, only commits made on or
// before it are returned, so Commits(..., until, 1) is "the last commit before that moment".
func (c *Client) Commits(ctx context.Context, owner, name, branch string, until time.Time, perPage int) ([]Commit, error) {
	q := url.Values{}
	q.Set("sha", branch)
	q.Set("per_page", fmt.Sprint(perPage))
	if !until.IsZero() {
		q.Set("until", until.UTC().Format(time.RFC3339))
	}
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

// TreeAt returns every file as of a commit (or branch), with each file's content id.
func (c *Client) TreeAt(ctx context.Context, owner, name, ref string) (SnapshotTree, error) {
	var t SnapshotTree
	err := c.get(ctx, repoPath(owner, name)+"/git/trees/"+url.PathEscape(ref)+"?recursive=1", &t)
	return t, err
}

// maxFileBytes is the biggest file we read through the contents call (GitHub's own limit is 1 MB).
const maxFileBytes = 1 << 20

// File returns the text of one file as of a branch. It is for small files such as dependency lists.
func (c *Client) File(ctx context.Context, owner, name, path, ref string) (string, error) {
	var f struct {
		Type     string `json:"type"`
		Size     int    `json:"size"`
		Encoding string `json:"encoding"`
		Content  string `json:"content"`
	}
	q := url.Values{}
	q.Set("ref", ref)
	if err := c.get(ctx, repoPath(owner, name)+"/contents/"+escapePath(path)+"?"+q.Encode(), &f); err != nil {
		return "", err
	}
	if f.Type != "file" || f.Encoding != "base64" || f.Size > maxFileBytes {
		return "", ErrNotFound
	}
	raw, err := base64.StdEncoding.DecodeString(strings.NewReplacer("\n", "", "\r", "").Replace(f.Content))
	if err != nil {
		return "", fmt.Errorf("read GitHub file: %w", err)
	}
	return string(raw), nil
}

func escapePath(p string) string {
	parts := strings.Split(p, "/")
	for i, s := range parts {
		parts[i] = url.PathEscape(s)
	}
	return strings.Join(parts, "/")
}
