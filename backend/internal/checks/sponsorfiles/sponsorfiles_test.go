package sponsorfiles_test

import (
	"testing"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/checks/sponsorfiles"
)

const pkg = `{"name":"stripe-fan-club","description":"supabase is great",
 "dependencies":{"react":"18","@stripe/stripe-js":"1","@google-cloud/storage":"6"},
 "devDependencies":{"vite":"5"}}`

func names(m []sponsorfiles.Match) []string {
	var out []string
	for _, x := range m {
		out = append(out, x.File+":"+x.Dependency)
	}
	return out
}

func TestAToolIsFoundByTheNameOfADependency(t *testing.T) {
	files := map[string]string{"package.json": pkg}
	if got := names(sponsorfiles.Find("Stripe", files)); len(got) != 1 || got[0] != "package.json:@stripe/stripe-js" {
		t.Errorf("Stripe: %v", got)
	}
	if got := names(sponsorfiles.Find("Google Cloud", files)); len(got) != 1 || got[0] != "package.json:@google-cloud/storage" {
		t.Errorf("Google Cloud: %v", got)
	}
}

func TestOnlyDependenciesCountNotTheProjectNameOrDescription(t *testing.T) {
	// "stripe" is in the project's name and "supabase" in its description, but neither is a dependency.
	files := map[string]string{"package.json": pkg}
	if got := sponsorfiles.Find("Supabase", files); len(got) != 0 {
		t.Errorf("Supabase should not match: %v", got)
	}
}

func TestOtherDependencyFormats(t *testing.T) {
	files := map[string]string{
		"requirements.txt": "# a comment about twilio\nflask==3.0\ntwilio>=8.0\n",
		"api/go.mod":       "module x\n\nrequire (\n\tgithub.com/stripe/stripe-go/v76 v76.1.0\n)\n",
	}
	if got := names(sponsorfiles.Find("Twilio", files)); len(got) != 1 || got[0] != "requirements.txt:twilio>=8.0" && got[0] != "requirements.txt:twilio" {
		t.Errorf("Twilio: %v", got)
	}
	if got := sponsorfiles.Find("Stripe", files); len(got) == 0 || got[0].File != "api/go.mod" {
		t.Errorf("Stripe in go.mod: %v", got)
	}
}

func TestATooShortNameIsNeverMatchedAndNothingToReadMeansNoMatch(t *testing.T) {
	if got := sponsorfiles.Find("AI", map[string]string{"package.json": `{"dependencies":{"main-ai-lib":"1"}}`}); got != nil {
		t.Errorf("short name: %v", got)
	}
	if got := sponsorfiles.Find("Stripe", nil); len(got) != 0 {
		t.Errorf("no files: %v", got)
	}
}
