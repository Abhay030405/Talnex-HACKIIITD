import { claimsTimeline } from "@/lib/claims-format";
import { BADGE_CLASS } from "@/lib/format";
import { insightTone } from "@/lib/insights";
import type { ClaimsVsGithub as Claims } from "@/lib/types";

/** What the resume says about a project (dates, team, role) beside the repository's GitHub history. Evidence only. */
export function ClaimsVsGithub({ claims }: { claims?: Claims | null }) {
  if (!claims) return <p className="note">The resume gives no dates or team for this project.</p>;
  const { claimed, actual, insights } = claims;
  const line = claimsTimeline(claimed, actual);
  const total = (actual?.contributors ?? []).reduce((sum, c) => sum + c.commits, 0);
  return (
    <div className="stack">
      <p className="note">What the resume says, set beside the repository history. Hints to look at, never part of the score.</p>
      <dl className="definition">
        <dt>Resume says</dt>
        <dd>
          {[claimed.start && `${claimed.start} to ${claimed.end ?? claimed.start}`, claimed.team, claimed.team_size &&
            `team of ${claimed.team_size}`, claimed.role && `role: ${claimed.role}`].filter(Boolean).join(" · ") || "No dates or team given"}
        </dd>
        <dt>GitHub shows</dt>
        <dd>
          {actual
            ? `${actual.first_commit?.slice(0, 10) ?? "?"} to ${actual.last_commit?.slice(0, 10) ?? "?"} · ${actual.commit_count} commits`
            : claims.reason || "The repository history was not read."}
        </dd>
      </dl>
      {line && (
        <div className="claims-timeline" aria-label="Claimed dates and commit dates on one timeline">
          <span className="claims-timeline__label">Resume</span>
          <span className="claims-timeline__track">
            <span className={`claims-timeline__bar claims-timeline__bar--claimed claims-timeline__at--${line.claimed[0]} claims-timeline__w--${line.claimed[1]}`} />
          </span>
          <span className="claims-timeline__label">GitHub</span>
          <span className="claims-timeline__track">
            <span className={`claims-timeline__bar claims-timeline__bar--actual claims-timeline__at--${line.actual[0]} claims-timeline__w--${line.actual[1]}`} />
          </span>
          <span className="meta">{line.from} — {line.to}</span>
        </div>
      )}
      {total > 0 && (
        <ul className="report-list">
          {actual!.contributors.map((c) => (
            <li key={c.login}>
              <strong>{c.login}</strong> <span className="meta">{Math.round((c.commits / total) * 100)}% · {c.commits} commits</span>
            </li>
          ))}
        </ul>
      )}
      {insights.map((i, n) => (
        <p className="row" key={n}>
          <span className={BADGE_CLASS[insightTone(i.evidence.tone).badge]}>{insightTone(i.evidence.tone).text}</span>
          <span>{i.evidence.summary}</span>
        </p>
      ))}
    </div>
  );
}
