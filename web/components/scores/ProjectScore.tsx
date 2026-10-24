import { formatCoverage, formatScore } from "@/lib/report-format";
import type { ProjectTalnex } from "@/lib/types";

/** A project's TalNex score out of 10, always shown with how much of the project was actually tested. */
export function ProjectScore({ talnex }: { talnex: ProjectTalnex }) {
  if (talnex.score10 === null) {
    return (
      <div className="project-score">
        <span className="badge badge--neutral">No score</span>
        <span className="project-score__note">Not enough could be tested to give a score.</span>
      </div>
    );
  }
  return (
    <div className="project-score">
      <span className="project-score__value">
        {formatScore(talnex.score10)}
        <span className="project-score__of">/10 TalNex score</span>
      </span>
      <span className="project-score__note">
        {talnex.features_scored} of {talnex.features_total} features scored · coverage {formatCoverage(talnex.coverage)}
      </span>
      {talnex.low_coverage && (
        <span className="project-score__note project-score__note--warn">
          Low coverage: only a small part could be tested, so read this score with care.
        </span>
      )}
    </div>
  );
}
