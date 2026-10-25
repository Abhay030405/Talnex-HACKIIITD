// Readable lines for the LeetCode Code Replay signals (ai/talnex_ai/coding/leetcode_capture). Hints, never proof.
import type { CodingSignal } from "@/lib/types";

export interface PasteCard {
  title: string;
  lines: string[];
  reason: string;
  snippet: string;
  link: string | null;
  linkText: string;
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string => (typeof v === "string" ? v : "");

/** One suspicious paste as a short card, or null for any other signal. */
export function pasteCard(signal: CodingSignal): PasteCard | null {
  if (signal.signal !== "leetcode_paste") return null;
  const e = signal.evidence;
  const at = str(e.at) || "?";
  const lines = [`Pasted ${num(e.lines) ?? "?"} lines at ${at}, ${num(e.edits_after) ?? 0} edits after`];
  const idle = num(e.idle_before_s);
  if (idle !== null && idle >= 60) lines.push(`Editor quiet for ${idle}s just before`);
  const jump = num(e.rating_jump);
  if (jump !== null && jump >= 100) lines.push(`+${jump} rating that contest`);
  const same = (e.same_code ?? null) as Record<string, unknown> | null;
  if (same) {
    const compared = num(same.compared);
    lines.push(
      compared !== null
        ? `Same code as ${num(same.matches) ?? 0} of ${compared} nearby contestants (closest ${num(same.best_pct) ?? 0}%)`
        : str(same.reason) || "Nearby contestants could not be checked",
    );
  }
  const problem = signal.problem || str(e.problem);
  return {
    title: [signal.contest, problem].filter(Boolean).join(" · ") || "LeetCode contest",
    lines,
    reason: str(e.reason),
    snippet: str(e.snippet),
    link: str(e.ranking_url) || null,
    linkText: `Open the contest ranking (replay at ${at})`,
  };
}

/** The one-line summary of the replay check, or null for any other signal. */
export function replaySummary(signal: CodingSignal): string | null {
  if (signal.signal !== "leetcode_replay") return null;
  const e = signal.evidence;
  const contests = Array.isArray(e.contests_checked) ? e.contests_checked.length : 0;
  return `Code Replay: ${contests} contests and ${num(e.replays_read) ?? 0} problem replays read, ${num(e.pastes) ?? 0} pastes, ${num(e.suspicious_pastes) ?? 0} worth a look.`;
}
