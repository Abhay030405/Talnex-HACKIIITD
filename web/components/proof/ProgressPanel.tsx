import { BADGE_CLASS } from "@/lib/format";
import { stageLabel, stageState } from "@/lib/progress-format";
import type { CandidateProgress, ProgressStage } from "@/lib/types";

function Stages({ stages }: { stages: ProgressStage[] }) {
  return (
    <ul className="progress-chips">
      {stages.map((stage) => {
        const state = stageState(stage.state);
        return (
          <li key={stage.name} className="progress-chip">
            <span className="progress-chip__label">{stageLabel(stage.name)}</span>
            <span className={BADGE_CLASS[state.tone]}>{state.text}</span>
            {stage.note && stage.state !== "done" && <span className="progress-chip__note">{stage.note}</span>}
          </li>
        );
      })}
    </ul>
  );
}

/** Each stage of the check with where it is, for the candidate and for each of their projects. */
export function ProgressPanel({ progress }: { progress: CandidateProgress }) {
  const empty = progress.stages.length === 0 && progress.projects.length === 0;
  return (
    <section className="panel" aria-labelledby="progress-title">
      <div className="panel__head">
        <h2 className="panel__title" id="progress-title">
          Progress
        </h2>
      </div>
      <div className="panel__body stack stack--tight" aria-live="polite">
        {progress.status_detail && <p className="note">{progress.status_detail}</p>}
        {empty && <p className="note">Nothing has started yet.</p>}
        <ul className="progress-list">
          {progress.stages.length > 0 && (
            <li className="progress-row">
              <span className="progress-row__name">The candidate</span>
              <Stages stages={progress.stages} />
            </li>
          )}
          {progress.projects.map((project) => (
            <li key={project.id} className="progress-row">
              <span className="progress-row__name">{project.name || "Project"}</span>
              <Stages stages={project.stages} />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
