import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { ContactSheet } from "@/components/landing/ContactSheet";

/** The sign-in pages' frame: the form on paper, and a still of the film strip beside it (hidden on phones). */
export function AuthFrame({ back, children }: { back: { href: string; label: string }; children: React.ReactNode }) {
  return (
    <div className="auth">
      <div className="auth__main">
        <div className="auth__inner">
          <Link href={back.href} className="auth__back">
            <ArrowLeft size={16} aria-hidden="true" />
            {back.label}
          </Link>
          {children}
        </div>
      </div>

      <aside className="auth__aside" aria-label="What a TalNex check looks like">
        <ContactSheet still only={[2, 3, 4]} />
        <p className="auth__caption">
          Every step is kept as a screenshot. A claim is only called broken after three tries and a second check.
        </p>
      </aside>
    </div>
  );
}
