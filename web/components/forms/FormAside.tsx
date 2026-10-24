/** The panel beside a creation form: what happens next, and a few things worth knowing. */
export function FormAside({ steps, notes }: { steps: string[]; notes: string[] }) {
  return (
    <aside className="form-layout__aside">
      <section className="panel" aria-labelledby="aside-next">
        <div className="panel__head">
          <h2 className="panel__title" id="aside-next">
            What happens next
          </h2>
        </div>
        <ol className="aside__steps panel__body">
          {steps.map((step, index) => (
            <li key={step} className="aside__step">
              <span className="aside__num" aria-hidden="true">
                {index + 1}
              </span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel" aria-labelledby="aside-notes">
        <div className="panel__head">
          <h2 className="panel__title" id="aside-notes">
            Good to know
          </h2>
        </div>
        <ul className="aside__notes panel__body">
          {notes.map((note) => (
            <li key={note} className="aside__note">
              {note}
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
