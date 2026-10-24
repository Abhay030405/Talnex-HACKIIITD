import { formatScore, scoreLevel } from "@/lib/report-format";

/** A feature score out of 10, coloured by level: 7 and up high, 4 to under 7 medium, below 4 low. */
export function ScoreChip({ score }: { score: number }) {
  return (
    <span className={`score-chip score-chip--${scoreLevel(score)}`} aria-label={`${formatScore(score)} out of 10`}>
      {formatScore(score)}
      <span className="score-chip__of" aria-hidden="true">
        /10
      </span>
    </span>
  );
}
