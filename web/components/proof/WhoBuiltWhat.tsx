import { accountLabel, whoBuiltWhatRows } from "@/lib/authorship-format";
import type { WhoBuiltWhatRow } from "@/lib/types";

/** Each GitHub account against the features it wrote most of. No percentages, no ranking, not part of any score. */
export function WhoBuiltWhat({ rows }: { rows?: WhoBuiltWhatRow[] | null }) {
  const shown = whoBuiltWhatRows(rows);
  if (shown.length === 0) return null;
  return (
    <section className="panel" aria-labelledby="who-built-title">
      <div className="panel__head">
        <h2 className="panel__title" id="who-built-title">
          Who built what
        </h2>
      </div>
      <div className="table__wrap">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">GitHub account</th>
              <th scope="col">Features it wrote most of</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.account} className="table__row--static">
                <td>{accountLabel(row.account)}</td>
                <td className="table__wrap-text">{row.features.join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="panel__foot note">
        From GitHub records. An account is not proof of a person. This is not a ranking and not part of any score.
      </p>
    </section>
  );
}
