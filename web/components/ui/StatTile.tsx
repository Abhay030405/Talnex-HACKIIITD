/** One number with a label, for the row at the top of a workspace. `highlight` marks a number that needs action. */
export function StatTile({
  label,
  value,
  hint,
  highlight = false,
}: {
  label: string;
  value: number | string;
  hint?: string;
  highlight?: boolean;
}) {
  return (
    <div className={highlight ? "stat stat--highlight" : "stat"}>
      <span className="stat__label">{label}</span>
      <span className="stat__value">{value}</span>
      {hint && <span className="stat__hint">{hint}</span>}
    </div>
  );
}
