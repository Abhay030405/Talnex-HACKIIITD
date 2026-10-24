import type { SandboxFacts } from "@/lib/types";

const n = (v: unknown) => (typeof v === "number" ? v : null);
const s = (v: unknown) => (typeof v === "string" && v ? v : null);

/** What the VM (sandbox) track did with the repository: started or why not, routes, tests, code review, logs. */
export function VmTestPanel({ sandbox }: { sandbox?: SandboxFacts | null }) {
  if (!sandbox) return <p className="note">The repository was not run in a VM for this project.</p>;
  const st = sandbox.stages ?? {};
  const routes = st.route_discovery ?? {};
  const api = st.sandbox_test ?? {};
  const repoTests = st.repo_tests ?? {};
  const review = st.code_review ?? {};
  const mechanisms = (review.mechanisms ?? {}) as Record<string, number>;

  return (
    <div className="stack">
      {sandbox.no_live_link && <p className="notice">No live link: tested in a VM from the repository.</p>}
      <dl className="definition">
        <dt>Started</dt>
        <dd>
          {sandbox.ran
            ? `Yes${sandbox.stack ? `, as a ${sandbox.stack} app` : ""}${sandbox.needed_a_fix ? " (after a fix to the start recipe)" : ""}`
            : `No: ${sandbox.reason || sandbox.detail || "it could not be run"}. This is never counted against anyone.`}
        </dd>
        {sandbox.recipe_source && (
          <>
            <dt>How it was started</dt>
            <dd>{sandbox.recipe_source.replace(/_/g, " ")}</dd>
          </>
        )}
        <dt>Routes</dt>
        <dd>
          {sandbox.routes_found ?? n(routes.routes) ?? 0} found
          {sandbox.spec_found ? " from an API document" : ""}
          {n(routes.notes_count) ? ` · ${routes.notes_count} notes` : ""}
        </dd>
        <dt>Routes tested</dt>
        <dd>
          {api.skipped
            ? `not tested: ${s(api.reason) ?? "nothing to test"}`
            : [n(api.passed) !== null && `${api.passed} passed`, n(api.failed) !== null && `${api.failed} failed`, n(api.tests) !== null && `${api.tests} tests`]
                .filter(Boolean)
                .join(" · ") || "no result"}
        </dd>
        <dt>The repository&apos;s own tests</dt>
        <dd>
          {repoTests.skipped
            ? `not run: ${s(repoTests.reason) ?? ""}`
            : `${n(repoTests.passed) ?? 0} passed · ${n(repoTests.failed) ?? 0} failed${s(repoTests.reason) ? ` (${repoTests.reason})` : ""}`}
        </dd>
        <dt>Code review</dt>
        <dd>
          {n(review.reviewed) !== null
            ? `${review.reviewed} of ${review.of ?? "?"} claims reviewed from code${
                Object.keys(mechanisms).length
                  ? ` · ${Object.entries(mechanisms)
                      .map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`)
                      .join(", ")}`
                  : ""
              }`
            : "not reviewed"}
        </dd>
      </dl>
      {sandbox.notes && sandbox.notes.length > 0 && (
        <ul className="report-list">
          {sandbox.notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      )}
      <div className="row">
        {sandbox.build_log_url && (
          <a className="meta" href={sandbox.build_log_url} target="_blank" rel="noopener noreferrer">
            Open the build log
          </a>
        )}
        {sandbox.run_log_url && (
          <a className="meta" href={sandbox.run_log_url} target="_blank" rel="noopener noreferrer">
            Open the run log
          </a>
        )}
      </div>
    </div>
  );
}
