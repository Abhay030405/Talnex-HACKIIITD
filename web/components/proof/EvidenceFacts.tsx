import { Fragment } from "react";

import type { EvidenceFact } from "@/lib/report-format";

/** Evidence facts as label and value rows; lists of records as a small table, objects as nested rows. */
export function EvidenceFacts({ facts }: { facts: EvidenceFact[] }) {
  if (facts.length === 0) return null;
  return (
    <dl className="definition">
      {facts.map((fact) => (
        <Fragment key={fact.label}>
          <dt>{fact.label}</dt>
          <dd>
            {fact.value}
            {fact.rows && <EvidenceFacts facts={fact.rows} />}
            {fact.table && (
              <div className="table__wrap">
                <table className="table table--compact">
                  <thead>
                    <tr>
                      {fact.table.columns.map((c) => (
                        <th key={c} scope="col">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {fact.table.rows.map((row, i) => (
                      <tr key={i} className="table__row--static">
                        {row.map((cell, j) => (
                          <td key={j}>{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </dd>
        </Fragment>
      ))}
    </dl>
  );
}
