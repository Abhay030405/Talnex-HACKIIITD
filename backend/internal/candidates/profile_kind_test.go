package candidates

import "testing"

// "x" (X / Twitter) is a one-letter link name the resume reader saves; confirming must accept it.
func TestProfileLinkNamesIncludeOneLetterX(t *testing.T) {
	for _, kind := range []string{"x", "github", "linkedin", "geeksforgeeks", "devto"} {
		in := Confirmation{
			Projects:     []FoundProject{{Name: "P"}},
			ProfileLinks: map[string]string{kind: "https://example.com/me"},
		}
		if _, err := in.check(); err != nil {
			t.Errorf("%q should be a valid link name: %v", kind, err)
		}
	}
	for _, kind := range []string{"", "1x", "has space", "waytoolongnameforalinkkind"} {
		in := Confirmation{Projects: []FoundProject{{Name: "P"}}, ProfileLinks: map[string]string{kind: "https://example.com"}}
		if _, err := in.check(); err == nil {
			t.Errorf("%q should be refused", kind)
		}
	}
}
