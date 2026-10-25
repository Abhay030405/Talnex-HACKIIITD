import { PageHero } from "@/components/ui/PageHero";

export interface DocSection {
  id: string;
  title: string;
  body: React.ReactNode;
}

/** A long reading page (terms, privacy): the hero, a list of sections that stays in view, and the text. */
export function DocPage({
  title,
  lead,
  updated,
  sections,
}: {
  title: string;
  lead: string;
  updated: string;
  sections: DocSection[];
}) {
  return (
    <>
      <PageHero title={title} lead={lead} meta={`Last updated ${updated}`} />
      <div className="doc wrap">
        <nav className="doc__toc" aria-label="On this page">
          <ol>
            {sections.map((s) => (
              <li key={s.id}>
                <a className="doc__toc-link" href={`#${s.id}`}>
                  {s.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>
        <article className="doc__body prose">
          {sections.map((s, i) => (
            <section key={s.id} id={s.id} className="doc__section">
              <h2 className="doc__heading">
                <span className="doc__num">{i + 1}</span>
                {s.title}
              </h2>
              {s.body}
            </section>
          ))}
        </article>
      </div>
    </>
  );
}
