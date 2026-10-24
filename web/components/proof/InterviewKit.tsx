import type { InterviewQuestion } from "@/lib/types";

const KIND_LABEL: Record<InterviewQuestion["kind"], string> = {
  coding: "Coding profile",
  feature: "Tested feature",
  flag: "Flag",
  demo: "Ask for a demo",
  skill: "Role skill",
};

/** Up to five questions for the interview, each with why it is worth asking. Things to talk about, not verdicts. */
export function InterviewKit({ questions }: { questions: InterviewQuestion[] }) {
  if (questions.length === 0) return null;
  return (
    <section className="panel" aria-labelledby="interview-title">
      <div className="panel__head">
        <h2 className="panel__title" id="interview-title">
          Interview kit
        </h2>
      </div>
      <div className="panel__body stack">
        <p className="note">Questions built from what TalNex found. Each is something to talk about, not a verdict.</p>
        <ol className="interview-kit">
          {questions.map((q, i) => (
            <li className="interview-kit__item" key={i}>
              <span className="meta">{KIND_LABEL[q.kind] ?? q.kind}</span>
              <p className="interview-kit__question">{q.question}</p>
              <p className="note">Why ask: {q.why}</p>
              {q.proof.ranking_url && (
                <a className="meta" href={q.proof.ranking_url} target="_blank" rel="noopener noreferrer">
                  Open the contest ranking{q.proof.at ? ` (replay at ${q.proof.at})` : ""}
                </a>
              )}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
