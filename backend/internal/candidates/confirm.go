package candidates

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"regexp"
	"strings"
)

// ErrNotWaiting means the recruiter tried to confirm a check that is not waiting for confirmation.
var ErrNotWaiting = errors.New("this check is not waiting for confirmation")

// ErrBadInput is a problem with what the recruiter sent. Its text is safe to show.
type ErrBadInput string

func (e ErrBadInput) Error() string { return string(e) }

const (
	maxProjects    = 8
	maxNameChars   = 120
	maxBulletChars = 400
)

var handlePattern = regexp.MustCompile(`^[A-Za-z0-9_.\-]{2,40}$`)

// profileHosts says, per coding site, which address it lives at and how to write the profile link.
var profileHosts = map[string]struct {
	domain string
	link   string
}{
	"codeforces": {"codeforces.com", "https://codeforces.com/profile/%s"},
	"leetcode":   {"leetcode.com", "https://leetcode.com/u/%s"},
	"codechef":   {"codechef.com", "https://www.codechef.com/users/%s"},
}

// leetcodePaths are LeetCode pages that are not a person.
var leetcodePaths = map[string]bool{
	"problems": true, "problemset": true, "contest": true, "explore": true, "discuss": true, "store": true,
	"interview": true, "studyplan": true, "accounts": true, "subscribe": true, "assessment": true, "u": true,
}

// ParseProfile takes what the recruiter typed for one coding site (a handle or a profile link) and returns the handle
// and the profile link. Empty input means "none" and returns two empty strings.
func ParseProfile(site, input string) (handle, link string, err error) {
	host, known := profileHosts[site]
	if !known {
		return "", "", ErrBadInput(fmt.Sprintf("unknown coding site %q", site))
	}
	input = strings.TrimSpace(input)
	if input == "" {
		return "", "", nil
	}
	if strings.Contains(input, "/") || strings.Contains(strings.ToLower(input), host.domain) {
		raw := input
		if !strings.Contains(raw, "://") {
			raw = "https://" + raw
		}
		u, perr := url.Parse(raw)
		hostname := ""
		if perr == nil {
			hostname = strings.TrimPrefix(strings.ToLower(u.Hostname()), "www.")
		}
		if perr != nil || hostname != host.domain {
			return "", "", ErrBadInput(fmt.Sprintf("that is not a %s profile address", host.domain))
		}
		segs := []string{}
		for _, seg := range strings.Split(u.Path, "/") {
			if seg != "" {
				segs = append(segs, seg)
			}
		}
		switch site {
		case "codeforces":
			if len(segs) >= 2 && strings.EqualFold(segs[0], "profile") {
				handle = segs[1]
			}
		case "codechef":
			if len(segs) >= 2 && strings.EqualFold(segs[0], "users") {
				handle = segs[1]
			}
		case "leetcode":
			if len(segs) >= 2 && strings.EqualFold(segs[0], "u") {
				handle = segs[1]
			} else if len(segs) >= 1 && !leetcodePaths[strings.ToLower(segs[0])] {
				handle = segs[0]
			}
		}
		if handle == "" {
			return "", "", ErrBadInput(fmt.Sprintf("that address does not point to a %s profile", host.domain))
		}
	} else {
		handle = input
	}
	if !handlePattern.MatchString(handle) {
		return "", "", ErrBadInput(fmt.Sprintf("%s: the handle can only use letters, numbers, dots, dashes and underscores", site))
	}
	return handle, fmt.Sprintf(host.link, handle), nil
}

// cleanLink checks a project link the recruiter typed; empty means none.
func cleanLink(label, raw string) (string, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return "", nil
	}
	if !strings.Contains(raw, "://") {
		raw = "https://" + raw
	}
	u, err := url.Parse(raw)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || !strings.Contains(u.Hostname(), ".") {
		return "", ErrBadInput(fmt.Sprintf("%s is not a web address", label))
	}
	return raw, nil
}

// FoundProject is a project as shown and edited on the confirm page.
type FoundProject struct {
	ID       string   `json:"id,omitempty"`
	Name     string   `json:"name"`
	LiveURL  string   `json:"live_url"`
	RepoURL  string   `json:"repo_url"`
	VideoURL string   `json:"video_url"`
	Bullets  []string `json:"bullets,omitempty"` // read only: what the resume says, shown for context
	// What the resume says about when and by whom it was built, compared later with the GitHub history.
	ClaimedStart    string `json:"claimed_start"`
	ClaimedEnd      string `json:"claimed_end"`
	ClaimedTeam     string `json:"claimed_team"`
	ClaimedTeamSize int    `json:"claimed_team_size"`
	ClaimedRole     string `json:"claimed_role"`
}

var claimedDate = regexp.MustCompile(`^\d{4}(-(0[1-9]|1[0-2]))?$`)

// checkClaims tidies a project's claimed dates, team and role, or says what is wrong in plain words.
func checkClaims(p *FoundProject) error {
	p.ClaimedStart, p.ClaimedEnd = strings.TrimSpace(p.ClaimedStart), strings.ToLower(strings.TrimSpace(p.ClaimedEnd))
	p.ClaimedTeam, p.ClaimedRole = strings.ToLower(strings.TrimSpace(p.ClaimedTeam)), strings.TrimSpace(p.ClaimedRole)
	switch {
	case p.ClaimedStart != "" && !claimedDate.MatchString(p.ClaimedStart):
		return ErrBadInput(p.Name + ": the start must look like 2026 or 2026-03")
	case p.ClaimedEnd != "" && p.ClaimedEnd != "present" && !claimedDate.MatchString(p.ClaimedEnd):
		return ErrBadInput(p.Name + ": the end must look like 2026, 2026-03 or present")
	case p.ClaimedTeam != "" && p.ClaimedTeam != "solo" && p.ClaimedTeam != "team":
		return ErrBadInput(p.Name + ": the team must be solo or team")
	case p.ClaimedTeamSize < 0 || p.ClaimedTeamSize > 99:
		return ErrBadInput(p.Name + ": the team size must be between 1 and 99")
	case len([]rune(p.ClaimedRole)) > 40:
		return ErrBadInput(p.Name + ": the role is too long")
	}
	return nil
}

// Found is what the resume reader found, for the recruiter to confirm.
type Found struct {
	Status        string            `json:"status"`
	StatusDetail  string            `json:"status_detail"`
	RoleLevel     string            `json:"role_level"`
	Projects      []FoundProject    `json:"projects"`
	CodingHandles map[string]string `json:"coding_handles"`
	CodingLinks   map[string]string `json:"coding_links"`
	// ProfileLinks are GitHub, LinkedIn, portfolio and other profile pages on the resume: kind -> address. Never email
	// or phone numbers.
	ProfileLinks map[string]string `json:"profile_links"`
}

// Confirmation is the confirmed list the recruiter sends back.
type Confirmation struct {
	Projects       []FoundProject    `json:"projects"`
	CodingProfiles map[string]string `json:"coding_profiles"` // site -> handle or profile link; empty removes it
	// ProfileLinks replaces the profile links when sent (kind -> http(s) address; empty removes it). Nil keeps them.
	ProfileLinks map[string]string `json:"profile_links"`
}

type confirmed struct {
	projects []FoundProject
	handles  map[string]string
	links    map[string]string
	profiles map[string]string // nil: keep what is saved
}

const maxProfileLinks = 15

var profileKind = regexp.MustCompile(`^[a-z][a-z0-9_]{1,19}$`)

// check turns the recruiter's input into clean values or a plain-words problem.
func (c Confirmation) check() (confirmed, error) {
	out := confirmed{handles: map[string]string{}, links: map[string]string{}}
	if len(c.Projects) == 0 {
		return out, ErrBadInput("add at least one project to check")
	}
	if len(c.Projects) > maxProjects {
		return out, ErrBadInput(fmt.Sprintf("at most %d projects can be checked", maxProjects))
	}
	names := map[string]bool{}
	for _, p := range c.Projects {
		name := strings.Join(strings.Fields(p.Name), " ")
		if name == "" {
			return out, ErrBadInput("every project needs a name")
		}
		if len([]rune(name)) > maxNameChars {
			return out, ErrBadInput("a project name is too long")
		}
		if names[strings.ToLower(name)] {
			return out, ErrBadInput(fmt.Sprintf("two projects are called %q", name))
		}
		names[strings.ToLower(name)] = true
		live, err := cleanLink(name+": the live link", p.LiveURL)
		if err != nil {
			return out, err
		}
		repo, err := cleanLink(name+": the code link", p.RepoURL)
		if err != nil {
			return out, err
		}
		video, err := cleanLink(name+": the video link", p.VideoURL)
		if err != nil {
			return out, err
		}
		fp := FoundProject{ID: p.ID, Name: name, LiveURL: live, RepoURL: repo, VideoURL: video, ClaimedStart: p.ClaimedStart,
			ClaimedEnd: p.ClaimedEnd, ClaimedTeam: p.ClaimedTeam, ClaimedTeamSize: p.ClaimedTeamSize, ClaimedRole: p.ClaimedRole}
		if err := checkClaims(&fp); err != nil {
			return out, err
		}
		out.projects = append(out.projects, fp)
	}
	for site, input := range c.CodingProfiles {
		handle, link, err := ParseProfile(site, input)
		if err != nil {
			return out, err
		}
		if handle != "" {
			out.handles[site] = handle
			out.links[site] = link
		}
	}
	if c.ProfileLinks != nil {
		out.profiles = map[string]string{}
		for kind, raw := range c.ProfileLinks {
			kind = strings.ToLower(strings.TrimSpace(kind))
			if !profileKind.MatchString(kind) {
				return out, ErrBadInput(fmt.Sprintf("%q is not a link name", kind))
			}
			link, err := cleanLink("the "+kind+" link", raw)
			if err != nil {
				return out, err
			}
			if link != "" {
				out.profiles[kind] = link
			}
		}
		if len(out.profiles) > maxProfileLinks {
			return out, ErrBadInput(fmt.Sprintf("at most %d profile links", maxProfileLinks))
		}
	}
	return out, nil
}

// Found returns what was read from the resume. The caller has already checked the owner.
func (s *Store) Found(ctx context.Context, candidateID string) (Found, error) {
	var (
		f                        Found
		handles, links, profiles []byte
	)
	err := s.pool.QueryRow(ctx, `
		SELECT status, coalesce(status_detail, ''), role_level, coding_handles, coding_links, profile_links
		  FROM candidates WHERE id = $1::uuid`, candidateID).Scan(&f.Status, &f.StatusDetail, &f.RoleLevel, &handles, &links, &profiles)
	if err != nil {
		return Found{}, fmt.Errorf("read candidate: %w", err)
	}
	f.CodingHandles, f.CodingLinks = map[string]string{}, map[string]string{}
	if err := json.Unmarshal(handles, &f.CodingHandles); err != nil {
		return Found{}, fmt.Errorf("read coding handles: %w", err)
	}
	if err := json.Unmarshal(links, &f.CodingLinks); err != nil {
		return Found{}, fmt.Errorf("read coding links: %w", err)
	}
	f.ProfileLinks = map[string]string{}
	if err := json.Unmarshal(profiles, &f.ProfileLinks); err != nil {
		return Found{}, fmt.Errorf("read profile links: %w", err)
	}
	f.Projects = []FoundProject{}
	rows, err := s.pool.Query(ctx, `
		SELECT id::text, name, coalesce(live_url, ''), coalesce(repo_url, ''), coalesce(video_url, ''), bullets,
		       coalesce(claimed_start, ''), coalesce(claimed_end, ''), coalesce(claimed_team, ''),
		       coalesce(claimed_team_size, 0), coalesce(claimed_role, '')
		  FROM candidate_projects WHERE candidate_id = $1::uuid ORDER BY created_at, id`, candidateID)
	if err != nil {
		return Found{}, fmt.Errorf("read projects: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var p FoundProject
		if err := rows.Scan(&p.ID, &p.Name, &p.LiveURL, &p.RepoURL, &p.VideoURL, &p.Bullets, &p.ClaimedStart, &p.ClaimedEnd,
			&p.ClaimedTeam, &p.ClaimedTeamSize, &p.ClaimedRole); err != nil {
			return Found{}, err
		}
		for i, b := range p.Bullets {
			if len([]rune(b)) > maxBulletChars {
				p.Bullets[i] = string([]rune(b)[:maxBulletChars])
			}
		}
		f.Projects = append(f.Projects, p)
	}
	return f, rows.Err()
}

// Confirm saves the recruiter's final list while the check waits: projects are updated, added or removed, and the
// coding profiles are replaced. It returns the ids of the projects to check. The check is not started here.
func (s *Store) Confirm(ctx context.Context, candidateID string, in Confirmation) ([]string, error) {
	c, err := in.check()
	if err != nil {
		return nil, err
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("begin confirm: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	var status string
	if err := tx.QueryRow(ctx, `SELECT status FROM candidates WHERE id = $1::uuid FOR UPDATE`, candidateID).Scan(&status); err != nil {
		return nil, ErrNotFound
	}
	if status != "awaiting_confirmation" {
		return nil, ErrNotWaiting
	}
	existing := map[string]bool{}
	rows, err := tx.Query(ctx, `SELECT id::text FROM candidate_projects WHERE candidate_id = $1::uuid`, candidateID)
	if err != nil {
		return nil, fmt.Errorf("read projects: %w", err)
	}
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			rows.Close()
			return nil, err
		}
		existing[id] = true
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, err
	}

	ids := []string{}
	for _, p := range c.projects {
		var id string
		switch {
		case p.ID != "" && existing[p.ID]:
			// Keep the project and apply the recruiter's edits.
			if _, err := tx.Exec(ctx, `
				UPDATE candidate_projects SET name = $2, live_url = NULLIF($3, ''), repo_url = NULLIF($4, ''), video_url = NULLIF($5, '')
				 WHERE id = $1::uuid`, p.ID, p.Name, p.LiveURL, p.RepoURL, p.VideoURL); err != nil {
				return nil, fmt.Errorf("update project: %w", err)
			}
			id = p.ID
		case p.ID != "":
			return nil, ErrBadInput("a project in the list does not belong to this check")
		default:
			// A project with this name may exist from the read (the recruiter re-typed it): reuse it.
			err := tx.QueryRow(ctx, `
				SELECT id::text FROM candidate_projects WHERE candidate_id = $1::uuid AND lower(name) = lower($2)`,
				candidateID, p.Name).Scan(&id)
			if err == nil {
				if _, err := tx.Exec(ctx, `
					UPDATE candidate_projects SET live_url = NULLIF($2, ''), repo_url = NULLIF($3, ''), video_url = NULLIF($4, '')
					 WHERE id = $1::uuid`, id, p.LiveURL, p.RepoURL, p.VideoURL); err != nil {
					return nil, fmt.Errorf("update project: %w", err)
				}
			} else if err := tx.QueryRow(ctx, `
				INSERT INTO candidate_projects (candidate_id, name, live_url, repo_url, video_url)
				VALUES ($1::uuid, $2, NULLIF($3, ''), NULLIF($4, ''), NULLIF($5, '')) RETURNING id::text`,
				candidateID, p.Name, p.LiveURL, p.RepoURL, p.VideoURL).Scan(&id); err != nil {
				return nil, fmt.Errorf("add project: %w", err)
			}
		}
		// A confirm with no claim fields at all (an older form) keeps what the resume reader found.
		noClaims := p.ClaimedStart == "" && p.ClaimedEnd == "" && p.ClaimedTeam == "" && p.ClaimedTeamSize == 0 && p.ClaimedRole == ""
		if noClaims {
			ids = append(ids, id)
			continue
		}
		if _, err := tx.Exec(ctx, `
			UPDATE candidate_projects SET claimed_start = NULLIF($2, ''), claimed_end = NULLIF($3, ''),
			       claimed_team = NULLIF($4, ''), claimed_team_size = NULLIF($5, 0), claimed_role = NULLIF($6, '')
			 WHERE id = $1::uuid`, id, p.ClaimedStart, p.ClaimedEnd, p.ClaimedTeam, p.ClaimedTeamSize, p.ClaimedRole); err != nil {
			return nil, fmt.Errorf("save project claims: %w", err)
		}
		ids = append(ids, id)
	}
	if _, err := tx.Exec(ctx, `DELETE FROM candidate_projects WHERE candidate_id = $1::uuid AND NOT (id::text = ANY($2))`,
		candidateID, ids); err != nil {
		return nil, fmt.Errorf("remove projects: %w", err)
	}
	handles, _ := json.Marshal(c.handles)
	links, _ := json.Marshal(c.links)
	if _, err := tx.Exec(ctx, `
		UPDATE candidates SET coding_handles = $2::jsonb, coding_links = $3::jsonb, updated_at = now() WHERE id = $1::uuid`,
		candidateID, handles, links); err != nil {
		return nil, fmt.Errorf("save coding profiles: %w", err)
	}
	if c.profiles != nil {
		profiles, _ := json.Marshal(c.profiles)
		if _, err := tx.Exec(ctx, `UPDATE candidates SET profile_links = $2::jsonb WHERE id = $1::uuid`, candidateID, profiles); err != nil {
			return nil, fmt.Errorf("save profile links: %w", err)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, fmt.Errorf("commit confirm: %w", err)
	}
	return ids, nil
}

// ReadRun is the run number of the latest resume read; every stage of that check uses the same number.
func (s *Store) ReadRun(ctx context.Context, candidateID string) (int, error) {
	var run int
	err := s.pool.QueryRow(ctx, `
		SELECT coalesce(max(run_number), 1) FROM jobs WHERE pipeline = 'recruiter_candidate' AND target_id = $1::uuid`,
		candidateID).Scan(&run)
	if err != nil {
		return 0, fmt.Errorf("find run: %w", err)
	}
	return run, nil
}

// MarkStarted moves a confirmed check on from "waiting" once its jobs are queued.
func (s *Store) MarkStarted(ctx context.Context, candidateID string) error {
	_, err := s.pool.Exec(ctx, `
		UPDATE candidates SET status = 'prechecking', status_detail = NULL, updated_at = now()
		 WHERE id = $1::uuid AND status = 'awaiting_confirmation'`, candidateID)
	if err != nil {
		return fmt.Errorf("mark started: %w", err)
	}
	return nil
}
