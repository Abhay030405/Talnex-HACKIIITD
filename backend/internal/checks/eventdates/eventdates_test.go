package eventdates_test

import (
	"testing"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/checks/eventdates"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/github"
)

func blob(path, sha string, size int) github.TreeNode {
	return github.TreeNode{Path: path, Type: "blob", SHA: sha, Size: size}
}

func TestCountsLeavesOutLibrariesBuildOutputAndPictures(t *testing.T) {
	for path, want := range map[string]bool{
		"src/app.js": true, "api/convert.py": true, "README.md": true,
		"node_modules/react/index.js": false, "web/node_modules/x/y.js": false, "dist/bundle.js": false,
		"package-lock.json": false, "public/logo.png": false, "static/app.min.js": false, "vendor/lib/a.go": false,
	} {
		if got := eventdates.Counts(path); got != want {
			t.Errorf("Counts(%q) = %v, want %v", path, got, want)
		}
	}
}

func TestShareIsByContentAndSize(t *testing.T) {
	before := []github.TreeNode{blob("a.js", "1", 300), blob("b.js", "2", 100)}
	final := []github.TreeNode{
		blob("a.js", "1", 300),               // unchanged since before the start
		blob("b.js", "9", 100),               // changed
		blob("c.js", "3", 100),               // new
		blob("node_modules/x.js", "4", 9999), // not the team's code
		{Path: "src", Type: "tree"},
	}
	r := eventdates.Compare(final, before)
	if r.FilesTotal != 3 || r.FilesBefore != 1 || r.TotalBytes != 500 || r.BeforeBytes != 300 || r.SharePct != 60 {
		t.Errorf("got %+v", r)
	}
}

func TestAMovedFileCountsAsNewAndNothingBeforeMeansZero(t *testing.T) {
	r := eventdates.Compare([]github.TreeNode{blob("new/a.js", "1", 10)}, []github.TreeNode{blob("old/a.js", "1", 10)})
	if r.SharePct != 0 {
		t.Errorf("moved file: %+v", r)
	}
	if r := eventdates.Compare([]github.TreeNode{blob("a.js", "1", 10)}, nil); r.SharePct != 0 || r.FilesTotal != 1 {
		t.Errorf("no earlier snapshot: %+v", r)
	}
	if r := eventdates.Compare(nil, nil); r.SharePct != 0 || r.FilesTotal != 0 {
		t.Errorf("nothing at all: %+v", r)
	}
}

func TestOneBigUpload(t *testing.T) {
	end := time.Date(2026, 11, 2, 9, 0, 0, 0, time.UTC)
	at := func(h, m int) github.Commit { return github.Commit{Date: time.Date(2026, 11, 2, h, m, 0, 0, time.UTC)} }
	cases := []struct {
		name    string
		commits []github.Commit
		seenAll bool
		want    bool
	}{
		{"one commit near the deadline", []github.Commit{at(8, 30)}, true, true},
		{"all within an hour near the deadline", []github.Commit{at(8, 50), at(8, 20)}, true, true},
		{"spread over hours", []github.Commit{at(8, 50), at(5, 0)}, true, false},
		{"one commit long before the deadline", []github.Commit{{Date: end.Add(-48 * time.Hour)}}, true, false},
		{"history cut short is never called a big upload", []github.Commit{at(8, 50), at(8, 40)}, false, false},
		{"no commits", nil, true, false},
	}
	for _, c := range cases {
		if got := eventdates.OneBigUpload(c.commits, c.seenAll, end); got != c.want {
			t.Errorf("%s: got %v, want %v", c.name, got, c.want)
		}
	}
}
