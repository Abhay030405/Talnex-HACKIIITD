import { weightedFromGroups } from "@/lib/role-score";
import { FlagList } from "@/components/flags/FlagBadge";
import { ClaimRow } from "@/components/proof/ClaimRow";
import { EngineeringQuality } from "@/components/proof/EngineeringQuality";
import { WalkthroughBox } from "@/components/proof/WalkthroughBox";
import { WhoBuiltWhat } from "@/components/proof/WhoBuiltWhat";
import { ProjectScore } from "@/components/scores/ProjectScore";
import { BADGE_CLASS, runLine } from "@/lib/format";
import { checkRows, groupKindLabel } from "@/lib/hackathon-format";
import { formatCoverage, formatScore } from "@/lib/report-format";
import type { AiOpinion, HackathonCard, OpinionPart } from "@/lib/types";

const OPINION_LABEL = "AI opinion — not tested proof";

function OpinionParts({ title, parts, note }: { title: string; parts: OpinionPart[]; note: string | null }) {
  return (
    <div className="stack stack--tight">
      <h3 className="card__title">{title}</h3>
      {note && <p className="note">The two models disagree on some parts, so read these with care.</p>}
      <ul className="plain-list stack stack--tight">
        {parts.map((part) => (
          <li key={part.part} className="opinion__part">
            <span className="opinion__name">{part.part}</span>
            <span className="meta">{part.score === null ? "No opinion" : `${formatScore(part.score)}/10`}</span>
            {part.disagree && <span className="badge badge--warning">Models disagree</span>}
            {part.reason && <span className="note">{part.reason}</span>}
            {part.proof_url && (
              <a className="meta" href={part.proof_url} target="_blank" rel="noopener noreferrer">
                Screenshot it looked at
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The AI's view of the UI and the idea. Always labelled, kept apart, and never part of any score. */
function OpinionBox({ opinion }: { opinion: AiOpinion }) {
  return (
    <section className="panel opinion" aria-labelledby="opinion-title">
      <div className="panel__head">
        <h2 className="panel__title" id="opinion-title">
          {opinion.label || OPINION_LABEL}
        </h2>
      </div>
      <div className="panel__body stack">
        <p className="note">This is a model&apos;s opinion. It is not tested proof and is never part of any score.</p>
        {opinion.ui ? (
          <OpinionParts title="UI" parts={opinion.ui.parts} note={opinion.ui.disagreement_note} />
        ) : (
          opinion.ui_note && <p className="note">UI: {opinion.ui_note}.</p>
        )}
        {opinion.innovation && (
          <OpinionParts title="Idea" parts={opinion.innovation.parts} note={opinion.innovation.disagreement_note} />
        )}
      </div>
    </section>
  );
}

/** One hackathon project's proof card: scores with coverage, flags beside them, each claim with proof, and notes. */
export function HackathonCardView({
  card,
  criteria,
}: {
  card: HackathonCard;
  /** The event's weights as they are now: the weighted total is worked out from them, so edits apply at once. */
  criteria?: { name: string; weight: number }[];
}) {
  const weighted =
    card.weighted_total && criteria?.length
      ? { ...card.weighted_total, ...weightedFromGroups(card.groups, criteria) }
      : card.weighted_total;

  return (
    <div className="stack">
      <section className="panel" aria-labelledby="card-title">
        <div className="panel__head project-card__head">
          <div className="stack stack--tight">
            <h2 className="panel__title" id="card-title">
              {card.team_name}
            </h2>
            <div className="row">
              {card.links.live && (
                <a className="meta" href={card.links.live} target="_blank" rel="noopener noreferrer">
                  Live site
                </a>
              )}
              {card.links.repo && (
                <a className="meta" href={card.links.repo} target="_blank" rel="noopener noreferrer">
                  Repository
                </a>
              )}
              {card.links.video && (
                <a className="meta" href={card.links.video} target="_blank" rel="noopener noreferrer">
                  Demo video
                </a>
              )}
            </div>
            {card.run && <p className="meta">{runLine(card.run)}</p>}
          </div>
          <ProjectScore talnex={card.talnex} />
        </div>

        <div className="panel__body stack">
          {weighted && (
            <div className="weighted">
              <span className="weighted__value">
                {weighted.score === null ? "–" : formatScore(weighted.score / 10)}
                <span className="project-score__of">/10 weighted total</span>
              </span>
              <span className="note">
                {weighted.label}. {weighted.criteria_used} of {weighted.criteria_total} criteria had tested claims.
              </span>
            </div>
          )}

          {card.groups.length > 0 && (
            <div className="table__wrap">
              <table className="table">
                <caption className="sr-only">Scores by group</caption>
                <thead>
                  <tr>
                    <th scope="col">Group</th>
                    <th scope="col">Kind</th>
                    <th scope="col">Score</th>
                    <th scope="col">Coverage</th>
                  </tr>
                </thead>
                <tbody>
                  {card.groups.map((g) => (
                    <tr key={g.group} className="table__row--static">
                      <td>{g.group}</td>
                      <td>{groupKindLabel(g.kind)}</td>
                      <td>{g.score === null ? "Not scored" : `${formatScore(g.score / 10)}/10`}</td>
                      <td>
                        {formatCoverage(g.coverage)}
                        {g.low_coverage && " · low"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <FlagList flags={card.flags} />

          {card.features.length > 0 && (
            <div className="claims">
              {card.features.map((feature) => (
                <ClaimRow key={feature.claim_id} feature={feature} />
              ))}
            </div>
          )}

          {card.features.length > 0 && <WalkthroughBox subject="project" subjectId={card.project_id} />}
        </div>
      </section>

      <EngineeringQuality engineering={card.engineering} />

      <WhoBuiltWhat rows={card.who_built_what} />

      {card.ai_opinion && <OpinionBox opinion={card.ai_opinion} />}

      {card.checks.length > 0 && (
        <section className="panel" aria-labelledby="checks-title">
          <div className="panel__head">
            <h2 className="panel__title" id="checks-title">
              Checks that did not run
            </h2>
          </div>
          <ul className="panel__body plain-list stack stack--tight">
            {checkRows(card.checks, Boolean(card.links.repo)).map((row, i) => (
              <li key={`${row.label}-${i}`} className="row">
                <span className={BADGE_CLASS[row.status === "failed" ? "danger" : "neutral"]}>
                  {row.status === "failed" ? "Could not finish" : "Skipped"}
                </span>
                <span>{row.label}</span>
                {row.reason && <span className="note">{row.reason}</span>}
                {row.stages && (
                  <span className="note">
                    ({row.stages.length} checks: {row.stages.join(", ")})
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {card.notes.length > 0 && (
        <ul className="report-list">
          {card.notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
