package candidates_test

import (
	"errors"
	"testing"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/candidates"
)

func TestParseProfile(t *testing.T) {
	good := []struct{ site, input, handle, link string }{
		{"leetcode", "asha_lc", "asha_lc", "https://leetcode.com/u/asha_lc"},
		{"leetcode", "https://leetcode.com/u/asha_lc/", "asha_lc", "https://leetcode.com/u/asha_lc"},
		{"leetcode", "leetcode.com/asha_lc", "asha_lc", "https://leetcode.com/u/asha_lc"},
		{"leetcode", "https://www.leetcode.com/u/asha_lc/?tab=1", "asha_lc", "https://leetcode.com/u/asha_lc"},
		{"codeforces", "https://codeforces.com/profile/Asha.V", "Asha.V", "https://codeforces.com/profile/Asha.V"},
		{"codeforces", "  tourist ", "tourist", "https://codeforces.com/profile/tourist"},
		{"codechef", "https://www.codechef.com/users/asha_cc", "asha_cc", "https://www.codechef.com/users/asha_cc"},
		{"codechef", "codechef.com/users/asha_cc", "asha_cc", "https://www.codechef.com/users/asha_cc"},
		{"codechef", "", "", ""},
	}
	for _, c := range good {
		handle, link, err := candidates.ParseProfile(c.site, c.input)
		if err != nil || handle != c.handle || link != c.link {
			t.Errorf("%s %q: got (%q, %q, %v), want (%q, %q)", c.site, c.input, handle, link, err, c.handle, c.link)
		}
	}

	bad := []struct{ site, input string }{
		{"leetcode", "https://leetcode.com/problems/two-sum"},   // a problem page, not a person
		{"leetcode", "https://leetcode.com/"},                   // no handle
		{"leetcode", "https://example.com/u/asha"},              // another website
		{"codeforces", "https://leetcode.com/u/asha"},           // the wrong site
		{"codechef", "https://www.codechef.com/problems/ABC"},   // not a profile
		{"codechef", "a"},                                       // too short
		{"codeforces", "has space"},                             // not a handle
		{"hackerrank", "asha"},                                  // not a site we read
	}
	for _, c := range bad {
		_, _, err := candidates.ParseProfile(c.site, c.input)
		var bad candidates.ErrBadInput
		if !errors.As(err, &bad) {
			t.Errorf("%s %q: expected a plain-words problem, got %v", c.site, c.input, err)
		}
	}
}
