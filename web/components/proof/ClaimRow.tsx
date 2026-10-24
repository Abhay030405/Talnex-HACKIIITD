import { ProofViewer } from "@/components/proof/ProofViewer";
import { FeatureScore } from "@/components/scores/FeatureScore";
import { BADGE_CLASS } from "@/lib/format";
import { confidenceLabel, verdictInfo } from "@/lib/report-format";
import type { ReportFeature } from "@/lib/types";

/** One claim: what was claimed, what happened on screen, how sure TalNex is, the score, and the proof. */
export function ClaimRow({ feature }: { feature: ReportFeature }) {
  const verdict = verdictInfo(feature.verdict);
  const confidence = confidenceLabel(feature.confidence);
  const notScored = feature.score10 === null;
  const notScoredReason =
    feature.untestable_reason || feature.reason || "This could not be tested. It does not count against anyone.";
  const review = feature.code_review;

  return (
    <article className="claim">
      <div className="claim__head">
        <div className="stack stack--tight">
          <h3 className="claim__text">{feature.text}</h3>
          <div className="row">
            <span className={BADGE_CLASS[verdict.tone]}>{verdict.text}</span>
            {confidence && <span className="meta">{confidence}</span>}
            {feature.group && <span className="meta">{feature.group}</span>}
          </div>
        </div>
        <FeatureScore
          score={feature.score10}
          reason={feature.score_reason}
          notScoredReason={notScored ? notScoredReason : null}
        />
      </div>

      {feature.reason && !notScored && <p className="claim__reason">{feature.reason}</p>}

      {review && (review.summary || review.mechanism) && (
        <div className="claim__review">
          <span className="badge badge--neutral">Reviewed from code, not run</span>
          {review.mechanism && <p className="note">How it works: {review.mechanism}</p>}
          {review.summary && <p className="note">{review.summary}</p>}
          {review.files_read.length > 0 && (
            <p className="note">
              Read: {review.files_read.slice(0, 6).join(", ")}
              {review.files_read.length > 6 ? ` and ${review.files_read.length - 6} more` : ""}
            </p>
          )}
        </div>
      )}

      <ProofViewer steps={feature.proof} />
    </article>
  );
}
