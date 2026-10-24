package http_test

import (
	"bufio"
	"os"
	"regexp"
	"sort"
	"strings"
	"testing"
)

// The API reference (backend/api/openapi.yaml) must match the routes server.go registers, both ways: a new route
// with no entry in the spec, or a spec entry for a route that is gone, fails here. No database needed.

var (
	routeLine    = regexp.MustCompile(`HandleFunc\("([A-Z]+) (/[^"]*)"`)
	specPathLine = regexp.MustCompile(`^  (/[^:\s]*):\s*$`)
	specVerbLine = regexp.MustCompile(`^    (get|put|post|delete|patch|head|options):`)
)

func serverRoutes(t *testing.T) map[string]bool {
	t.Helper()
	src, err := os.ReadFile("server.go")
	if err != nil {
		t.Fatal(err)
	}
	routes := map[string]bool{}
	for _, m := range routeLine.FindAllStringSubmatch(string(src), -1) {
		routes[m[1]+" "+m[2]] = true
	}
	if len(routes) < 30 {
		t.Fatalf("found only %d routes in server.go; has the way routes are registered changed?", len(routes))
	}
	return routes
}

// specRoutes reads the operations under `paths:` with a plain line scan (the spec uses two-space indents).
func specRoutes(t *testing.T) map[string]bool {
	t.Helper()
	f, err := os.Open("../../api/openapi.yaml")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	routes := map[string]bool{}
	inPaths, path := false, ""
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		if !strings.HasPrefix(line, " ") && strings.TrimSpace(line) != "" {
			inPaths = strings.HasPrefix(line, "paths:")
			continue
		}
		if !inPaths {
			continue
		}
		if m := specPathLine.FindStringSubmatch(line); m != nil {
			path = m[1]
		} else if m := specVerbLine.FindStringSubmatch(line); m != nil && path != "" {
			routes[strings.ToUpper(m[1])+" "+path] = true
		}
	}
	if err := sc.Err(); err != nil {
		t.Fatal(err)
	}
	return routes
}

func TestOpenAPICoversEveryRoute(t *testing.T) {
	server, spec := serverRoutes(t), specRoutes(t)
	var missing, stale []string
	for r := range server {
		if !spec[r] {
			missing = append(missing, r)
		}
	}
	for r := range spec {
		if !server[r] {
			stale = append(stale, r)
		}
	}
	sort.Strings(missing)
	sort.Strings(stale)
	if len(missing) > 0 {
		t.Errorf("routes in server.go missing from backend/api/openapi.yaml:\n  %s", strings.Join(missing, "\n  "))
	}
	if len(stale) > 0 {
		t.Errorf("routes in backend/api/openapi.yaml that server.go no longer has:\n  %s", strings.Join(stale, "\n  "))
	}
}
