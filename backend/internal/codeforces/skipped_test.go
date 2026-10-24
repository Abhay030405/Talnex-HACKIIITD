package codeforces

import (
	"testing"
	"time"
)

var now = time.Date(2026, 10, 21, 12, 0, 0, 0, time.UTC)

func daysAgo(d int) int64 { return now.Add(-time.Duration(d) * 24 * time.Hour).Unix() }

func rated(id int, days int, oldR, newR int) RatingChange {
	return RatingChange{ContestID: id, ContestName: "Round " + string(rune('A'+id)), OldRating: oldR, NewRating: newR, UpdateSec: daysAgo(days)}
}

func sub(contest int, kind, verdict string) Submission {
	s := Submission{ContestID: contest, Verdict: verdict}
	s.Author.ParticipantType = kind
	return s
}

func TestAllSkippedContestIsFound(t *testing.T) {
	ratings := []RatingChange{rated(1, 30, 1200, 1210)}
	subs := []Submission{sub(1, "CONTESTANT", "SKIPPED"), sub(1, "CONTESTANT", "SKIPPED"), sub(1, "CONTESTANT", "SKIPPED")}
	got := FindAllSkipped(ratings, subs, now)
	if len(got) != 1 || got[0].ContestID != 1 || got[0].Submissions != 3 {
		t.Errorf("got %v", got)
	}
}

func TestOneSkippedSubmissionIsIgnored(t *testing.T) {
	got := FindAllSkipped([]RatingChange{rated(1, 30, 1200, 1210)}, []Submission{sub(1, "CONTESTANT", "SKIPPED")}, now)
	if len(got) != 0 {
		t.Errorf("a single skipped submission is normal, got %v", got)
	}
}

func TestAnyNormalSubmissionClearsTheContest(t *testing.T) {
	subs := []Submission{sub(1, "CONTESTANT", "SKIPPED"), sub(1, "CONTESTANT", "SKIPPED"), sub(1, "CONTESTANT", "OK")}
	if got := FindAllSkipped([]RatingChange{rated(1, 30, 1200, 1210)}, subs, now); len(got) != 0 {
		t.Errorf("got %v", got)
	}
}

func TestPracticeAndVirtualSubmissionsAreRemovedFirst(t *testing.T) {
	// Skipped contest entries, plus practice solves of the same problems later: still all skipped.
	subs := []Submission{sub(1, "CONTESTANT", "SKIPPED"), sub(1, "CONTESTANT", "SKIPPED"),
		sub(1, "PRACTICE", "OK"), sub(1, "VIRTUAL", "OK")}
	if got := FindAllSkipped([]RatingChange{rated(1, 30, 1200, 1210)}, subs, now); len(got) != 1 {
		t.Errorf("practice solves must not hide a skipped contest, got %v", got)
	}
	// Only practice submissions: nothing to judge.
	only := []Submission{sub(1, "PRACTICE", "SKIPPED"), sub(1, "PRACTICE", "SKIPPED")}
	if got := FindAllSkipped([]RatingChange{rated(1, 30, 1200, 1210)}, only, now); len(got) != 0 {
		t.Errorf("got %v", got)
	}
}

func TestVeryRecentContestsAreNotJudgedYet(t *testing.T) {
	subs := []Submission{sub(1, "CONTESTANT", "SKIPPED"), sub(1, "CONTESTANT", "SKIPPED")}
	if got := FindAllSkipped([]RatingChange{rated(1, 1, 1200, 1210)}, subs, now); len(got) != 0 {
		t.Errorf("a contest from yesterday is still settling, got %v", got)
	}
}

func TestOnlyTheLastFiveContestsAndSuddenJumpsAreLookedAt(t *testing.T) {
	var ratings []RatingChange
	var subs []Submission
	for id := 1; id <= 8; id++ { // contest 1 is the oldest
		ratings = append(ratings, rated(id, 100-id*5, 1200, 1210))
		subs = append(subs, sub(id, "CONTESTANT", "SKIPPED"), sub(id, "CONTESTANT", "SKIPPED"))
	}
	got := FindAllSkipped(ratings, subs, now)
	if len(got) != 5 || got[0].ContestID != 4 || got[4].ContestID != 8 {
		t.Errorf("want contests 4 to 8, got %v", got)
	}
	// An old contest with a sudden jump is added.
	ratings[0] = rated(1, 95, 1200, 1500)
	got = FindAllSkipped(ratings, subs, now)
	if len(got) != 6 || got[0].ContestID != 1 {
		t.Errorf("want the jump contest too, got %v", got)
	}
}

func TestNoRatedContestsMeansNothingToJudge(t *testing.T) {
	if got := FindAllSkipped(nil, []Submission{sub(1, "CONTESTANT", "SKIPPED")}, now); got != nil {
		t.Errorf("got %v", got)
	}
}

func try(contest int, problem, verdict string, at int64) Submission {
	s := sub(contest, "CONTESTANT", verdict)
	s.Problem.Index, s.CreatedSec = problem, at
	return s
}

func TestASingleSkippedProblemWithoutAResubmissionIsFound(t *testing.T) {
	subs := []Submission{try(1, "A", "OK", 100), try(1, "B", "SKIPPED", 200), try(1, "C", "WRONG_ANSWER", 300)}
	got := FindPartlySkipped([]RatingChange{rated(1, 30, 1200, 1210)}, subs, now)
	if len(got) != 1 || got[0].Problem != "B" || got[0].Skipped != 1 || got[0].Resubmitted || got[0].ContestName == "" {
		t.Fatalf("got %+v", got)
	}
}

func TestASkipFollowedByAResubmissionIsMarkedResubmitted(t *testing.T) {
	subs := []Submission{try(1, "A", "SKIPPED", 100), try(1, "A", "OK", 200), try(1, "B", "SKIPPED", 300), try(1, "B", "OK", 50)}
	got := FindPartlySkipped([]RatingChange{rated(1, 30, 1200, 1210)}, subs, now)
	if len(got) != 2 || !got[0].Resubmitted || got[1].Resubmitted {
		t.Fatalf("A was resubmitted after its skip, B was not (its OK came earlier): %+v", got)
	}
}

func TestPartlySkippedLeavesWholeSkippedContestsPracticeAndRecentContestsAlone(t *testing.T) {
	ratings := []RatingChange{rated(1, 30, 1200, 1210), rated(2, 30, 1210, 1220), rated(3, 1, 1220, 1230)}
	practice := sub(2, "PRACTICE", "SKIPPED")
	subs := []Submission{try(1, "A", "SKIPPED", 1), try(1, "B", "SKIPPED", 2), // the whole contest: FindAllSkipped's job
		practice, try(2, "A", "OK", 3), // practice is not a contest entry
		try(3, "A", "OK", 4), try(3, "B", "SKIPPED", 5)} // ended a day ago: not judged yet
	if got := FindPartlySkipped(ratings, subs, now); len(got) != 0 {
		t.Fatalf("got %+v", got)
	}
}
