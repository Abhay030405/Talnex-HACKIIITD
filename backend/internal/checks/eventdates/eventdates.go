// Package eventdates works out how much of a hackathon project's final code already existed before the event began.
//
// It compares the final files with the files as of the last commit made before the start date. A file counts as
// "already there" only when it is at the same path with the same content. The check gives facts, never a verdict:
// commit dates can be set by the author, so GitHub's own record of when the repository was created is reported next to
// the share, and the flag levels (decided in Python) use both.
package eventdates

import (
	"path"
	"strings"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/github"
)

// Result is the share of the final code that was already there before the start.
type Result struct {
	TotalBytes  int     // size of the final code that was compared
	BeforeBytes int     // part of it that was unchanged since before the start
	SharePct    float64 // BeforeBytes / TotalBytes x 100, 0 when there is nothing to compare
	FilesTotal  int
	FilesBefore int
}

// skippedFolders hold code the team did not write: installed libraries, build output, generated files.
var skippedFolders = map[string]bool{
	"node_modules": true, "vendor": true, "dist": true, "build": true, ".next": true, "out": true, "target": true,
	"__pycache__": true, ".venv": true, "venv": true, ".git": true, ".idea": true, ".vscode": true, "coverage": true,
	"bower_components": true, "pods": true, ".gradle": true,
}

var skippedNames = map[string]bool{
	"package-lock.json": true, "yarn.lock": true, "pnpm-lock.yaml": true, "poetry.lock": true, "pipfile.lock": true,
	"cargo.lock": true, "go.sum": true, "composer.lock": true, "gemfile.lock": true, ".gitignore": true,
	".ds_store": true, "license": true, "license.md": true, "license.txt": true,
}

var skippedExtensions = map[string]bool{
	".png": true, ".jpg": true, ".jpeg": true, ".gif": true, ".svg": true, ".ico": true, ".webp": true, ".mp4": true,
	".mov": true, ".mp3": true, ".woff": true, ".woff2": true, ".ttf": true, ".eot": true, ".pdf": true, ".zip": true,
	".map": true, ".min.js": true, ".min.css": true,
}

// Counts reports whether a file is the team's own code. Libraries, build output, lock files, pictures and fonts are
// left out so a big starter template or a bundled library does not decide the answer.
func Counts(filePath string) bool {
	lower := strings.ToLower(filePath)
	for _, part := range strings.Split(path.Dir(lower), "/") {
		if skippedFolders[part] {
			return false
		}
	}
	if skippedNames[path.Base(lower)] {
		return false
	}
	for ext := range skippedExtensions {
		if strings.HasSuffix(lower, ext) {
			return false
		}
	}
	return true
}

// Compare says how much of the final code was already there in the earlier snapshot.
func Compare(final, before []github.TreeNode) Result {
	was := map[string]string{} // path -> content id, before the start
	for _, n := range before {
		if n.Type == "blob" {
			was[n.Path] = n.SHA
		}
	}
	var r Result
	for _, n := range final {
		if n.Type != "blob" || !Counts(n.Path) {
			continue
		}
		size := n.Size
		if size < 1 {
			size = 1 // an empty file still counts as a file
		}
		r.FilesTotal++
		r.TotalBytes += size
		if sha, ok := was[n.Path]; ok && sha == n.SHA {
			r.FilesBefore++
			r.BeforeBytes += size
		}
	}
	if r.TotalBytes > 0 {
		r.SharePct = float64(int(1000*float64(r.BeforeBytes)/float64(r.TotalBytes)+0.5)) / 10
	}
	return r
}

// OneBigUpload reports whether the whole history looks like a single push close to the deadline: every commit within
// one hour of each other, and the last one within 12 hours before the event ended (or after it).
// Fewer than two commits count as one push. A history that was cut short (more commits than we read) is never called
// a big upload, because we cannot see all of it.
func OneBigUpload(commits []github.Commit, seenAll bool, endsAt time.Time) bool {
	if len(commits) == 0 || !seenAll {
		return false
	}
	newest, oldest := commits[0].Date, commits[0].Date
	for _, c := range commits {
		if c.Date.After(newest) {
			newest = c.Date
		}
		if c.Date.Before(oldest) {
			oldest = c.Date
		}
	}
	return newest.Sub(oldest) <= time.Hour && !newest.Before(endsAt.Add(-12*time.Hour))
}
