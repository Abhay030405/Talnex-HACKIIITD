import { VerdictBadge, type VerdictKind } from "@/components/ui/VerdictBadge";

// A made-up result. The margin notes are the rules TalNex keeps (AGENTS.md section 1), written where they apply.
const ROWS: { text: string; score: string; kind: VerdictKind; reason: string; note?: string }[] = [
  {
    text: "Upload an image and get a caption",
    score: "8",
    kind: "works",
    reason: "Worked with 3 different images. Captions match the picture.",
  },
  {
    text: "Search past captions",
    score: "0",
    kind: "broken",
    reason: "Every search returns a server error.",
    note: "Failed 3 times and a second check agreed. Only then is it called broken.",
  },
  {
    text: "Share a caption by link",
    score: "5",
    kind: "partly",
    reason: "The link opens, but the image is missing.",
  },
  {
    text: "Sign in with a phone code",
    score: "–",
    kind: "untested",
    reason: "The code never arrived.",
    note: "Left out of the score. It never counts against anyone.",
  },
];

export function Specimen() {
  return (
    <section className="specimen wrap" id="proof" aria-labelledby="proof-title">
      <div className="specimen__intro">
        <h2 className="display-2" id="proof-title">
          The result, one row per claim
        </h2>
        <p className="specimen__lead">
          A sample proof card. Red flags sit next to the score and are never taken away from it. There is no ranking:
          people decide.
        </p>
      </div>

      <article className="proof-sheet">
        <header className="proof-sheet__head">
          <div>
            <h3 className="proof-sheet__name">CaptionBuddy</h3>
            <p className="proof-sheet__sub">3 of 4 features tested. 26 screenshots.</p>
          </div>
          <p className="proof-sheet__score">
            4.3<span className="proof-sheet__of">out of 10</span>
          </p>
        </header>

        <ul className="proof-sheet__rows">
          {ROWS.map((row) => (
            <li key={row.text} className="proof-row">
              <div className="proof-row__main">
                <span className="proof-row__claim">{row.text}</span>
                <span className="proof-row__reason">{row.reason}</span>
              </div>
              <span className={`proof-row__score proof-row__score--${row.kind}`}>{row.score}</span>
              <VerdictBadge kind={row.kind} />
              {row.note && <span className="proof-row__note">{row.note}</span>}
            </li>
          ))}
        </ul>
      </article>
    </section>
  );
}
