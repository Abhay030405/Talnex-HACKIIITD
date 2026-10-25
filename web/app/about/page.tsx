import type { Metadata } from "next";

import { ContactSheet } from "@/components/landing/ContactSheet";
import { PageHero } from "@/components/ui/PageHero";

export const metadata: Metadata = { title: "About" };

// The promises in AGENTS.md section 1, said plainly. They are product rules, not marketing.
const RULES = [
  {
    title: "Every number shows its proof",
    text: "Screenshots, the steps taken, how much was covered and how sure we are sit one click from each score.",
  },
  {
    title: "“Could not test” is never a fail",
    text: "When a site asks for a phone code that never arrives, that part is left out of the score and the reason is shown.",
  },
  {
    title: "Broken needs proof twice",
    text: "Three tries, a wait, and a second model that sees only the screenshots. If they disagree, it stays “could not confirm”.",
  },
  {
    title: "Flags sit beside the score",
    text: "Copied code or hidden text aimed at an AI checker is shown for a person to judge. It is never subtracted.",
  },
  {
    title: "People decide",
    text: "No overall ranking and no single winner. TalNex shows the evidence; organizers and recruiters make the call.",
  },
];

const NOT_YET = [
  "Testing mobile apps",
  "Reading Devpost galleries on its own",
  "Checking that a coding profile belongs to the candidate",
];

export default function AboutPage() {
  return (
    <>
      <PageHero
        title="Why TalNex exists"
        lead="A project link on a resume or a hackathon entry is a promise. Checking one by hand takes 10 to 15 minutes, so most never get checked at all."
      />

      <section className="about wrap" aria-labelledby="about-problem">
        <div className="about__cols">
          <h2 className="about__heading" id="about-problem">
            What goes wrong today
          </h2>
          <div className="prose">
            <p>
              Demo videos can be edited. Live sites break the week after judging. Resume filters read words, link
              checkers only see that a page loads, and code analysers never press a button. None of them tell you
              whether the thing actually works.
            </p>
            <p>
              Judges and recruiters end up trusting the confident README, or spending an evening clicking through
              projects one at a time.
            </p>
          </div>
        </div>
      </section>

      <section className="about-film" aria-labelledby="about-how">
        <div className="wrap about__cols">
          <h2 className="about__heading" id="about-how">
            What TalNex does instead
          </h2>
          <div className="prose">
            <p>
              An AI agent reads what the project claims, makes a test plan, then opens the live site and uses it like a
              real person: it signs up, clicks, types and uploads. It keeps a screenshot of every step, so every verdict
              comes with its evidence.
            </p>
          </div>
        </div>
        <ContactSheet />
      </section>

      <section className="about wrap" aria-labelledby="about-rules">
        <h2 className="display-2" id="about-rules">
          The rules it keeps
        </h2>
        <dl className="rules">
          {RULES.map((rule) => (
            <div key={rule.title} className="rules__item">
              <dt className="rules__title">{rule.title}</dt>
              <dd className="rules__text">{rule.text}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="about wrap" aria-labelledby="about-not">
        <div className="about__cols">
          <h2 className="about__heading" id="about-not">
            What it does not do yet
          </h2>
          <div className="prose">
            <ul>
              {NOT_YET.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <p>
              On a site it tests, it never pays, deletes anything or messages real users. Everything it creates is
              labelled “TalNex test”.
            </p>
          </div>
        </div>
      </section>
    </>
  );
}
