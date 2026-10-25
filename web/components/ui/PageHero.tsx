/** The top of an inner page: a condensed title with a china-marker underline that draws itself in, and a lead line. */
export function PageHero({ title, lead, meta }: { title: string; lead?: string; meta?: string }) {
  return (
    <header className="page-hero wrap">
      <h1 className="page-hero__title">{title}</h1>
      <svg className="marker-line page-hero__line" viewBox="0 0 300 12" preserveAspectRatio="none" aria-hidden="true">
        <path pathLength={1} d="M2 8 C 80 2, 200 12, 298 4" />
      </svg>
      {lead && <p className="page-hero__lead">{lead}</p>}
      {meta && <p className="page-hero__meta">{meta}</p>}
    </header>
  );
}
