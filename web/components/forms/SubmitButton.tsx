"use client";

import { useFormStatus } from "react-dom";

/** Turns itself off while the form is being sent, so a double click never sends it twice. */
export function SubmitButton({
  children,
  pendingText = "Saving…",
}: {
  children: React.ReactNode;
  pendingText?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className="button button--primary button--lg" disabled={pending} aria-busy={pending}>
      {pending ? pendingText : children}
    </button>
  );
}
