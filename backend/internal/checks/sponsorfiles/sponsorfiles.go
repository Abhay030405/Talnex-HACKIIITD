// Package sponsorfiles looks for an event's sponsor tools in a project's dependency files.
//
// "Listed in a dependency file" is only half of the question (the other half, "really called in a real feature",
// is checked in Python from the code). A tool that is not listed is not proof that it is unused: it may be called
// over plain HTTP. So this package reports what it found and never judges.
package sponsorfiles

import (
	"encoding/json"
	"regexp"
	"sort"
	"strings"
)

// Match is one dependency that belongs to a sponsor tool.
type Match struct {
	File       string `json:"file"`
	Dependency string `json:"dependency"`
}

var nonAlnum = regexp.MustCompile(`[^a-z0-9]+`)

// squash makes names comparable: "Google Cloud" and "@google-cloud/storage" both lose their punctuation.
func squash(s string) string { return nonAlnum.ReplaceAllString(strings.ToLower(s), "") }

// Names lists the dependency names in one dependency file. JSON manifests are read properly; for every other
// format the names are the word-like pieces of each line that is not a comment.
func Names(file, content string) []string {
	base := strings.ToLower(file[strings.LastIndex(file, "/")+1:])
	if base == "package.json" || base == "composer.json" {
		return jsonNames(content)
	}
	seen := map[string]bool{}
	var out []string
	word := regexp.MustCompile(`[A-Za-z0-9@][A-Za-z0-9@/_.\-]*`)
	for _, line := range strings.Split(content, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") || strings.HasPrefix(line, "//") {
			continue
		}
		for _, w := range word.FindAllString(line, -1) {
			if !seen[w] {
				seen[w] = true
				out = append(out, w)
			}
		}
	}
	return out
}

func jsonNames(content string) []string {
	var doc map[string]json.RawMessage
	if json.Unmarshal([]byte(content), &doc) != nil {
		return nil
	}
	var out []string
	for _, key := range []string{"dependencies", "devDependencies", "peerDependencies", "optionalDependencies", "require", "require-dev"} {
		var deps map[string]json.RawMessage
		if raw, ok := doc[key]; ok && json.Unmarshal(raw, &deps) == nil {
			for name := range deps {
				out = append(out, name)
			}
		}
	}
	sort.Strings(out)
	return out
}

// Find returns the dependencies of a sponsor tool: those whose squashed name contains the tool's squashed name.
// "Stripe" matches "stripe" and "@stripe/stripe-js"; "Google Cloud" matches "@google-cloud/storage".
func Find(tool string, files map[string]string) []Match {
	want := squash(tool)
	if len(want) < 3 { // too short to match by name without false hits
		return nil
	}
	var out []Match
	paths := make([]string, 0, len(files))
	for p := range files {
		paths = append(paths, p)
	}
	sort.Strings(paths)
	for _, p := range paths {
		for _, dep := range Names(p, files[p]) {
			if strings.Contains(squash(dep), want) {
				out = append(out, Match{File: p, Dependency: dep})
			}
		}
	}
	return out
}
