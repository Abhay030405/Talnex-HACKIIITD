import Link from "next/link";

import { ArrowIcon } from "@/components/ui/Icons";
import { Magnetic } from "@/components/ui/Magnetic";

type Variant = "primary" | "secondary" | "ghost";
type Size = "md" | "lg";

interface Common {
  variant?: Variant;
  size?: Size;
  /** Adds the arrow after the words, for links that move the person on. */
  arrow?: boolean;
  block?: boolean;
  children: React.ReactNode;
}

function classes({ variant = "secondary", size = "md", block = false }: Common): string {
  return ["btn", `btn--${variant}`, size === "lg" && "btn--lg", block && "btn--block"].filter(Boolean).join(" ");
}

function Inner({ children, arrow }: Pick<Common, "children" | "arrow">) {
  return (
    <>
      {children}
      {arrow && (
        <span className="btn__arrow">
          <ArrowIcon size={16} />
        </span>
      )}
    </>
  );
}

/** A link styled as a button. `magnetic` makes it lean toward the pointer, for the main call to action. */
export function ButtonLink({ href, magnetic = false, ...props }: Common & { href: string; magnetic?: boolean }) {
  const link = <PlainLink href={href} {...props} />;
  return magnetic ? <Magnetic>{link}</Magnetic> : link;
}

function PlainLink({ href, ...props }: Common & { href: string }) {
  const external = /^https?:\/\//.test(href);
  if (href.startsWith("#") || external) {
    return (
      <a href={href} className={classes(props)} {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
        <Inner {...props} />
      </a>
    );
  }
  return (
    <Link href={href} className={classes(props)}>
      <Inner {...props} />
    </Link>
  );
}

/** A real button: submits a form unless told otherwise. */
export function Button({
  type = "submit",
  disabled,
  onClick,
  ...props
}: Common & {
  type?: "submit" | "button";
  disabled?: boolean;
  onClick?: () => void;
}) {
  return (
    <button type={type} className={classes(props)} disabled={disabled} onClick={onClick}>
      <Inner {...props} />
    </button>
  );
}
