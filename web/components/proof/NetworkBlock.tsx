import { SLOW_MS } from "@/lib/network";
import type { DevtoolsRecord } from "@/lib/types";

/** What the browser's developer tools saw during one step. Evidence beside the verdict, never a verdict on its own. */
export function NetworkBlock({ devtools }: { devtools: DevtoolsRecord | null | undefined }) {
  if (!devtools) return null;
  const calls = devtools.api_calls ?? [];
  const failed = devtools.failed_requests ?? [];
  const consoleErrors = [...(devtools.console_errors ?? []), ...(devtools.page_errors ?? [])];
  const leaks = devtools.leaks ?? [];
  if (!calls.length && !failed.length && !consoleErrors.length && !leaks.length) return null;

  return (
    <details className="network">
      <summary>
        Network and console ({calls.length} API {calls.length === 1 ? "call" : "calls"}
        {leaks.length ? `, ${leaks.length} leaked` : ""})
      </summary>
      {leaks.length > 0 && (
        <ul className="report-list">
          {leaks.map((l, i) => (
            <li key={i} className="network__bad">
              Leaked {l.type.replace(/_/g, " ")}: {l.masked} <span className="meta">({l.where})</span>
            </li>
          ))}
        </ul>
      )}
      {calls.length > 0 && (
        <div className="table__wrap">
          <table className="table network__table">
            <thead>
              <tr>
                <th scope="col">Method</th>
                <th scope="col">Address</th>
                <th scope="col">Status</th>
                <th scope="col">Time</th>
              </tr>
            </thead>
            <tbody>
              {calls.map((c, i) => (
                <tr key={i} className={c.status >= 400 || (c.ms ?? 0) >= SLOW_MS ? "network__bad" : undefined}>
                  <td>{c.method}</td>
                  <td className="network__url">{c.url}</td>
                  <td>{c.status}</td>
                  <td>{c.ms === undefined ? "–" : `${c.ms} ms`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {failed.length > 0 && (
        <ul className="report-list">
          {failed.map((f, i) => (
            <li key={i} className="network__bad">
              Failed: {f.method} {f.url} ({f.error})
            </li>
          ))}
        </ul>
      )}
      {consoleErrors.length > 0 && (
        <ul className="report-list">
          {consoleErrors.map((e, i) => (
            <li key={i} className="network__console">
              {e}
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}
