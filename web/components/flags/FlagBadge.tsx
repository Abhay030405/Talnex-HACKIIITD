import { BADGE_CLASS } from "@/lib/format";
import { flagLevelInfo, flagTypeLabel, sortFlags } from "@/lib/report-format";
import type { FlagLevel, ReportFlag } from "@/lib/types";

/** One flag: how strong it is, what kind, and why. A flag sits beside a score and is never part of it. */
export function FlagBadge({ level, reason, type }: { level: FlagLevel; reason?: string; type?: string }) {
  const info = flagLevelInfo(level);
  return (
    <li className="flag">
      <span className={BADGE_CLASS[info.tone]}>{info.text}</span>
      {type && <span className="flag__name">{flagTypeLabel(type)}</span>}
      {reason && <span className="flag__reason">{reason}</span>}
    </li>
  );
}

/** Flags, strongest first, with the reminder that they are not subtracted from any score. */
export function FlagList({ flags }: { flags: ReportFlag[] }) {
  if (flags.length === 0) return null;
  return (
    <div className="flags">
      <p className="flags__note">Flags sit beside the score. They are never subtracted from it.</p>
      <ul className="flags__list">
        {sortFlags(flags).map((flag, i) => (
          <FlagBadge key={`${flag.type}-${i}`} level={flag.level} reason={flag.reason} type={flag.type} />
        ))}
      </ul>
    </div>
  );
}
