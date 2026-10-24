package r2

import "fmt"

// File locations on R2 (architecture section 22). Python builds the same keys in
// ai/talnex_ai/storage/keys.py; keep the two in step.

func ScreenKey(project, run string, step int) string {
	return fmt.Sprintf("screens/%s/%s/%d", project, run, step)
}

func VideoKey(project, name string) string {
	return fmt.Sprintf("videos/%s/%s", project, name)
}

func FrameKey(project, name string) string {
	return fmt.Sprintf("frames/%s/%s", project, name)
}

func ResumeKey(candidate, name string) string {
	return fmt.Sprintf("resumes/%s/%s", candidate, name)
}

func ResumePrefix(candidate string) string {
	return fmt.Sprintf("resumes/%s/", candidate)
}

func ReplayKey(candidate, contest, problem string) string {
	return fmt.Sprintf("replays/%s/%s/%s", candidate, contest, problem)
}

func SandboxKey(project, run, name string) string {
	return fmt.Sprintf("sandbox/%s/%s/%s", project, run, name)
}

// VoiceKey is a recorded walkthrough question (architecture section 31.5). It is deleted once turned into text.
func VoiceKey(owner, walkthrough string) string {
	return fmt.Sprintf("voice/%s/%s", owner, walkthrough)
}

func OpinionKey(project, name string) string {
	return fmt.Sprintf("opinion/%s/%s", project, name)
}
