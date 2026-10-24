import { ScoreChip } from "@/components/scores/ScoreChip";

// A made-up example for the landing page, so a visitor sees what a result looks like before signing in.
const FEATURES = [
  {
    name: "Upload an image and get a caption",
    score: 8,
    reason: "+ a real model call with retries and output checks; − no time limit on slow uploads.",
  },
  {
    name: "Search past captions",
    score: 5,
    reason: "+ works on normal searches; − empty and very long searches return a server error.",
  },
  {
    name: "Share a caption by link",
    score: 0,
    reason: "Broken: the share link returns “not found” after two tries, and a second check of the screenshots agreed.",
  },
];

export function ExampleProofCard() {
  return (
    <figure className="example-card" aria-label="Example proof card, made up for illustration">
      <div className="example-card__head">
        <div className="stack stack--tight">
          <span className="badge badge--neutral">Example result</span>
          <h3 className="card__title">CaptionBuddy</h3>
          <span className="meta">3 features tested · coverage 100%</span>
        </div>
        <div className="project-score">
          <span className="project-score__value">
            4.3<span className="project-score__of">/10 TalNex score</span>
          </span>
        </div>
      </div>
      {FEATURES.map((feature) => (
        <div className="example-card__row" key={feature.name}>
          <span className="example-card__feature">{feature.name}</span>
          <ScoreChip score={feature.score} />
          <p className="example-card__reason">{feature.reason}</p>
        </div>
      ))}
    </figure>
  );
}
