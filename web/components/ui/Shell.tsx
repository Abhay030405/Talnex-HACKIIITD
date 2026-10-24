import { signOut } from "@/auth";
import { LogoutIcon } from "@/components/ui/Icons";
import { Logo } from "@/components/ui/Logo";
import { ShellNav, type ShellNavItem } from "@/components/ui/ShellNav";
import { ROLE_NAMES, homePath, type Role } from "@/lib/types";

const NAV: Record<Role, ShellNavItem[]> = {
  recruiter: [
    { href: "/recruiter", label: "Candidates", icon: "users", also: ["/candidates"] },
    { href: "/new/recruiter", label: "New check", icon: "plus" },
  ],
  organizer: [
    { href: "/organizer", label: "Events", icon: "calendar", also: ["/events"] },
    { href: "/new/hackathon", label: "New event", icon: "plus" },
  ],
};

/** The signed-in frame: a sidebar with the role's own pages and a top bar with the person. */
export function Shell({ role, name, children }: { role: Role; name: string; children: React.ReactNode }) {
  async function leave() {
    "use server";
    await signOut({ redirectTo: "/" });
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="shell__side">
        <Logo href={homePath(role)} label="TalNex workspace home" />
        <span className="shell__section">{ROLE_NAMES[role]}</span>
        <ShellNav items={NAV[role]} />
        <p className="shell__note">Humans decide. TalNex shows the evidence.</p>
      </aside>

      <div className="shell__body">
        <header className="shell__top">
          <span className="shell__crumb">{ROLE_NAMES[role]} workspace</span>
          <div className="shell__user">
            <span className="shell__avatar" aria-hidden="true">
              {name.trim().slice(0, 1).toUpperCase() || "?"}
            </span>
            <span className="shell__name">{name}</span>
            <form action={leave}>
              <button type="submit" className="button button--ghost button--sm">
                <LogoutIcon size={16} />
                Sign out
              </button>
            </form>
          </div>
        </header>
        <main className="shell__main" id="main">
          {children}
        </main>
      </div>
    </div>
  );
}
