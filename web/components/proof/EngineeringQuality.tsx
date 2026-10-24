import type { Engineering } from "@/lib/types";

/** How the repository is built as engineering work: a bar per area, a summary, and evidence linked to GitHub. */
export function EngineeringQuality({ engineering }: { engineering?: Engineering | null }) {
  if (!engineering || engineering.areas.length === 0) return null;
  return (
    <details className="engineering">
      <summary className="engineering__head">
        <span>Engineering quality</span>
        <span className="meta">{engineering.overall === null ? "not scored" : `${engineering.overall} / 10`}</span>
      </summary>
      <p className="note">How the repository is built. Shown beside the feature scores, never subtracted from them.</p>
      <ul className="engineering__areas">
        {engineering.areas.map((a) => (
          <li className="engineering__area" key={a.area}>
            <div className="engineering__row">
              <strong>{a.label}</strong>
              <span className="meta">{a.score === null ? "–" : `${a.score} / 10`}</span>
            </div>
            <meter className="engineering__bar" min={0} max={10} low={4} high={7} optimum={10} value={a.score ?? 0} />
            <p className="note">{a.summary}</p>
            {a.evidence.length > 0 && (
              <ul className="report-list">
                {a.evidence.map((e, i) => {
                  const label = e.kind === "commit" ? `${e.sha} ${e.message ?? ""}` : e.path;
                  return (
                    <li key={i}>
                      {e.url ? (
                        <a className="meta" href={e.url} target="_blank" rel="noopener noreferrer">
                          {label}
                        </a>
                      ) : (
                        <span className="meta">{label}</span>
                      )}
                      {e.note ? ` — ${e.note}` : ""}
                    </li>
                  );
                })}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}
