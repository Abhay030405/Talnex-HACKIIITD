import Link from "next/link";

/** The TalNex mark and name. `small` is the footer size; `href` makes it a link home. */
export function Logo({
  href = "/",
  small = false,
  label = "TalNex home",
}: {
  href?: string | null;
  small?: boolean;
  label?: string;
}) {
  const body = (
    <>
      <span className={small ? "logo__mark logo__mark--small" : "logo__mark"} aria-hidden="true">
        T
      </span>
      {!small && <span className="logo__name">TalNex</span>}
    </>
  );
  if (!href) return <span className="logo">{body}</span>;
  return (
    <Link href={href} className="logo" aria-label={label}>
      {body}
    </Link>
  );
}
