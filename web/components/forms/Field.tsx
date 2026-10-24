/** A label, its input and an optional hint. The hint is tied to the input so screen readers read it too. */
export function Field({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {hint && (
        <span className="field__hint" id={`${htmlFor}-hint`}>
          {hint}
        </span>
      )}
    </div>
  );
}
