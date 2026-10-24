import { ScoreChip } from "@/components/scores/ScoreChip";

/** A feature's score with its one-line reason, or "not scored" with why. Not scored never counts against anyone. */
export function FeatureScore({
  score,
  reason,
  notScoredReason,
}: {
  score: number | null;
  reason?: string | null;
  notScoredReason?: string | null;
}) {
  if (score === null) {
    return (
      <div className="feature-score">
        <span className="badge badge--neutral">Not scored</span>
        <span className="feature-score__reason">
          {notScoredReason || "Left out of the score. It does not count against anyone."}
        </span>
      </div>
    );
  }
  return (
    <div className="feature-score">
      <ScoreChip score={score} />
      {reason && <span className="feature-score__reason">{reason}</span>}
    </div>
  );
}
