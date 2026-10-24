// Pure helpers for the tabbed report: verdict counts and groups, a project's authorship, and the GitHub activity card.
import type { AuthorshipAccount, CodingSignal, ReportFeature } from "@/lib/types";

export const VERDICT_ORDER = ["broken", "partly_works", "works", "reviewed_from_code", "could_not_test"] as const;
export type VerdictKey = (typeof VERDICT_ORDER)[number];

export const VERDICT_GROUP_TITLE: Record<VerdictKey, string> = {
  broken: "Broken",
  partly_works: "Partly works",
  works: "Works",
  reviewed_from_code: "Reviewed from code, not run",
  could_not_test: "Could not test (not counted against anyone)",
};

const key = (f: ReportFeature): VerdictKey => (f.verdict ?? "could_not_test") as VerdictKey;

/** How many features have each verdict, for the stacked bar. */
export function verdictCounts(features: ReportFeature[]): Record<VerdictKey, number> {
  const out = Object.fromEntries(VERDICT_ORDER.map((v) => [v, 0])) as Record<VerdictKey, number>;
  for (const f of features) out[key(f)] = (out[key(f)] ?? 0) + 1;
  return out;
}

/** The features grouped by verdict, worst first; empty groups left out. */
export function groupByVerdict(features: ReportFeature[]): { verdict: VerdictKey; features: ReportFeature[] }[] {
  return VERDICT_ORDER.map((verdict) => ({ verdict, features: features.filter((f) => key(f) === verdict) })).filter(
    (g) => g.features.length > 0,
  );
}

/** Who wrote the project's traced code: each account's lines and commits summed over the features, as a share. */
export function projectAuthorship(features: ReportFeature[]): (AuthorshipAccount & { share: number })[] {
  // ponytail: features can trace the same lines, so sums can count a line twice; read the shares as rough.
  const byAccount = new Map<string, AuthorshipAccount>();
  for (const f of features) {
    for (const a of f.authorship?.accounts ?? []) {
      const had = byAccount.get(a.account);
      byAccount.set(
        a.account,
        had
          ? { ...had, lines: had.lines + a.lines, commits: had.commits + a.commits,
              first_pushed_at: [had.first_pushed_at, a.first_pushed_at].filter(Boolean).sort()[0] ?? null,
              last_pushed_at: [had.last_pushed_at, a.last_pushed_at].filter(Boolean).sort().at(-1) ?? null }
          : { ...a },
      );
    }
  }
  const total = [...byAccount.values()].reduce((s, a) => s + a.lines, 0);
  return [...byAccount.values()]
    .map((a) => ({ ...a, share: total ? a.lines / total : 0 }))
    .sort((a, b) => b.lines - a.lines);
}

export interface GithubCardData {
  account: string;
  link: string;
  ageYears: number | null;
  since: string | null;
  publicRepos: number | null;
  originals: number | null;
  forks: number | null;
  oneDayRepos: number | null;
  reposSampled: number | null;
  commitsSampled: number | null;
  longestQuietMonths: number | null;
  languages: { name: string; repos: number }[];
  months: { month: string; commits: number; quiet: boolean; height: number }[];
  trend: "active" | "slowing" | "quiet";
  lastActive: string | null;
  repos: { repo: string; commits: number; activeDays: number; busiestShare: number; mostOnOneDay: boolean; atLeast: boolean }[];
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** The github_profile signal as a card: never shows raw evidence. Null when the signal has no account. */
export function githubCard(signal: CodingSignal | undefined): GithubCardData | null {
  const e = signal?.evidence ?? {};
  const account = typeof e.account === "string" ? e.account : "";
  if (!account) return null;
  const months = (Array.isArray(e.months) ? e.months : [])
    .filter((m): m is { month: string; commits: number } => typeof m === "object" && m !== null && "month" in m)
    .map((m) => ({ month: String(m.month), commits: Number(m.commits) || 0 }));
  const max = Math.max(1, ...months.map((m) => m.commits));
  const recent = months.slice(-3).reduce((s, m) => s + m.commits, 0);
  const before = months.slice(-6, -3).reduce((s, m) => s + m.commits, 0);
  const trend: GithubCardData["trend"] = recent === 0 ? "quiet" : before > 0 && recent < before / 2 ? "slowing" : "active";
  const lastActive = [...months].reverse().find((m) => m.commits > 0)?.month ?? null;
  const languages = Object.entries((e.languages as Record<string, number>) ?? {})
    .map(([name, repos]) => ({ name, repos: Number(repos) || 0 }))
    .sort((a, b) => b.repos - a.repos);
  const repos = (Array.isArray(e.repos) ? e.repos : [])
    .filter((r): r is Record<string, unknown> => typeof r === "object" && r !== null)
    .map((r) => ({
      repo: String(r.repo ?? ""),
      commits: Number(r.commits) || 0,
      activeDays: Number(r.active_days) || 0,
      busiestShare: Number(r.busiest_day_share) || 0,
      mostOnOneDay: Boolean(r.most_on_one_day),
      atLeast: Boolean(r.page_full),
    }));
  const age = num(e.account_age_days);
  return {
    account,
    link: `https://github.com/${encodeURIComponent(account)}`,
    ageYears: age === null ? null : Math.round((age / 365) * 10) / 10,
    since: typeof e.since === "string" ? e.since : null,
    publicRepos: num(e.public_repos),
    originals: num(e.originals),
    forks: num(e.forks),
    oneDayRepos: num(e.one_day_repos),
    reposSampled: num(e.repos_sampled),
    commitsSampled: num(e.commits_sampled),
    longestQuietMonths: num(e.longest_quiet_months),
    languages,
    months: months.map((m) => ({ ...m, quiet: m.commits === 0, height: Math.round((m.commits / max) * 100) })),
    trend,
    lastActive,
    repos,
  };
}
