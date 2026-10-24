import { NetworkBlock } from "@/components/proof/NetworkBlock";
import { proofInfo } from "@/lib/report-format";
import type { ProofStep } from "@/lib/types";

/**
 * The steps TalNex took. A screenshot opens larger on click (native details, no script). A backend step's saved request
 * and answer is a link, never a broken picture. Links are short-lived, so a page left open may need a refresh.
 */
export function ProofViewer({ steps }: { steps: ProofStep[] }) {
  if (steps.length === 0) return null;
  return (
    <details className="proof-viewer">
      <summary>
        See the proof ({steps.length} {steps.length === 1 ? "step" : "steps"})
      </summary>
      <ol className="proof-viewer__steps">
        {steps.map((step) => {
          const proof = proofInfo(step);
          return (
            <li className="proof-step" key={step.step}>
              <span className="proof-step__action">
                Step {step.step}: {step.action}
              </span>
              {step.observed && <span className="proof-step__observed">Seen: {step.observed}</span>}
              {proof.show === "image" && (
                <details className="shot">
                  <summary>
                    {/* A short-lived storage link: Next's image optimiser would cache it past its life. */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img className="shot__img" src={step.proof_url} alt={proof.text} loading="lazy" />
                  </summary>
                </details>
              )}
              {proof.show === "link" && (
                <a className="meta" href={step.proof_url} target="_blank" rel="noopener noreferrer">
                  {proof.text}
                </a>
              )}
              {proof.show === "none" && <span className="proof-step__observed">{proof.text}</span>}
              <NetworkBlock devtools={step.devtools} />
            </li>
          );
        })}
      </ol>
    </details>
  );
}
