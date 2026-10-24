import { formatDate } from "@/lib/format";
import type { GithubCardData } from "@/lib/report-layout";

const TREND: Record<GithubCardData["trend"], { text: string; badge: string }> = {
  active: { text: "Active", badge: "badge badge--success" },
  slowing: { text: "Slowing down", badge: "badge badge--warning" },
  quiet: { text: "Quiet lately", badge: "badge badge--neutral" },
};

const monthLabel = (m: string) => {
  const d = new Date(`${m}-01T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? m : d.toLocaleDateString("en-GB", { month: "short", year: "2-digit", timeZone: "UTC" });
};

/** The headline numbers, for the Overview tab. */
export function GithubSummary({ data }: { data: GithubCardData }) {
  const trend = TREND[data.trend];
  return (
    <div className="github-card">
      <div className="row">
        <a className="table__link" href={data.link} target="_blank" rel="noopener noreferrer">
          github.com/{data.account}
        </a>
        <span className={trend.badge}>{trend.text}</span>
      </div>
      <div className="github-card__numbers">
        {data.ageYears !== null && <Num label="Account age" value={`${data.ageYears} yr`} />}
        {data.publicRepos !== null && <Num label="Public repos" value={data.publicRepos} />}
        {data.originals !== null && <Num label="Original repos" value={data.originals} />}
        {data.lastActive && <Num label="Last active" value={monthLabel(data.lastActive)} />}
      </div>
      {data.languages.length > 0 && <Languages data={data} limit={5} />}
    </div>
  );
}

function Num({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="github-card__num">
      <span className="github-card__value">{value}</span>
      <span className="meta">{label}</span>
    </div>
  );
}

function Languages({ data, limit }: { data: GithubCardData; limit?: number }) {
  return (
    <div className="row">
      {data.languages.slice(0, limit).map((l) => (
        <span className="chip" key={l.name}>
          {l.name} · {l.repos}
        </span>
      ))}
    </div>
  );
}

/** The whole GitHub activity card, for the GitHub tab. Facts only, never a verdict: much work happens in private. */
export function GithubCard({ data }: { data: GithubCardData }) {
  return (
    <section className="panel" aria-labelledby="github-title">
      <div className="panel__head">
        <h2 className="panel__title" id="github-title">
          GitHub activity
        </h2>
      </div>
      <div className="panel__body stack">
        <GithubSummary data={data} />
        <div className="github-card__numbers">
          {data.forks !== null && <Num label="Forks" value={data.forks} />}
          {data.oneDayRepos !== null && <Num label="Repos made in one day" value={data.oneDayRepos} />}
          {data.reposSampled !== null && <Num label="Repos sampled" value={data.reposSampled} />}
          {data.commitsSampled !== null && <Num label="Commits sampled" value={data.commitsSampled} />}
          {data.longestQuietMonths !== null && <Num label="Longest quiet stretch" value={`${data.longestQuietMonths} mo`} />}
        </div>
        {data.since && <p className="meta">Activity since {formatDate(data.since)}.</p>}

        {data.months.length > 0 && (
          <figure className="github-bars" aria-label="Commits per month">
            <div className="github-bars__plot">
              {data.months.map((m) => (
                <div key={m.month} className="github-bars__col" title={`${monthLabel(m.month)}: ${m.commits} commits`}>
                  <span className="github-bars__count">{m.commits}</span>
                  <span
                    className={
                      m.quiet
                        ? "github-bars__bar github-bars__bar--quiet"
                        : `github-bars__bar github-bars__bar--h${Math.max(1, Math.ceil(m.height / 10))}`
                    }
                    aria-hidden="true"
                  />
                  <span className="github-bars__label">{monthLabel(m.month)}</span>
                </div>
              ))}
            </div>
            <figcaption className="meta">Commits per month (a grey bar is a month with none).</figcaption>
          </figure>
        )}

        {data.languages.length > 0 && (
          <div className="stack stack--tight">
            <span className="field__label">Main language of each original repo</span>
            <Languages data={data} />
          </div>
        )}

        {data.repos.length > 0 && (
          <div className="table__wrap">
            <table className="table table--compact">
              <thead>
                <tr>
                  <th scope="col">Repository</th>
                  <th scope="col">Commits</th>
                  <th scope="col">Active days</th>
                  <th scope="col">Busiest day</th>
                </tr>
              </thead>
              <tbody>
                {data.repos.map((r) => (
                  <tr key={r.repo} className="table__row--static">
                    <td>{r.repo}</td>
                    <td>
                      {r.commits}
                      {r.atLeast ? "+" : ""}
                    </td>
                    <td>{r.activeDays}</td>
                    <td>
                      {Math.round(r.busiestShare * 100)}%
                      {r.mostOnOneDay && <span className="badge badge--warning"> Mostly one day</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="note">Facts to look at, not a verdict. A quiet account is never a mark against anyone: much work is private.</p>
      </div>
    </section>
  );
}
