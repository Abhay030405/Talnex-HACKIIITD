import Link from "next/link";

import { BackIcon } from "@/components/ui/Icons";

/** The title block of every signed-in page. `back` puts a clear way out at the top. */
export function PageHeader({
  title,
  lead,
  back,
  actions,
  children,
}: {
  title: string;
  lead?: string;
  back?: { href: string; label: string };
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="page-header">
      {back && (
        <Link href={back.href} className="back-link page-header__back">
          <BackIcon />
          {back.label}
        </Link>
      )}
      <div className="page-header__row">
        <div>
          <h1 className="page-header__title">{title}</h1>
          {lead && <p className="page-header__lead">{lead}</p>}
        </div>
        {actions && <div className="page-header__actions">{actions}</div>}
      </div>
      {children}
    </div>
  );
}
