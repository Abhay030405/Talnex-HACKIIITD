import { BADGE_CLASS } from "@/lib/format";
import { flagLevelInfo, flagTypeLabel, groupFlags } from "@/lib/report-format";
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

/** Flags, strongest first, one line per kind (the reasons fold away when a kind repeats), with the reminder that
 * they are not subtracted from any score. */
export function FlagList({ flags }: { flags: ReportFlag[] }) {
  if (flags.length === 0) return null;
  return (
    <div className="flags">
      <p className="flags__note">Flags sit beside the score. They are never subtracted from it.</p>
      <ul className="flags__list">
        {groupFlags(flags).map((group) =>
          group.reasons.length === 1 ? (
            <FlagBadge key={group.type} level={group.level} reason={group.reasons[0]} type={group.type} />
          ) : (
            <li className="flag" key={group.type}>
              <span className={BADGE_CLASS[flagLevelInfo(group.level).tone]}>{flagLevelInfo(group.level).text}</span>
              <span className="flag__name">{flagTypeLabel(group.type)}</span>
              <details className="flag__more">
                <summary>{group.reasons.length} features</summary>
                <ul className="plain-list stack stack--tight">
                  {group.reasons.map((reason, i) => (
                    <li className="flag__reason" key={i}>
                      {reason}
                    </li>
                  ))}
                </ul>
              </details>
            </li>
          ),
        )}
      </ul>
    </div>
  );
}
