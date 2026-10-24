import Link from "next/link";

import { ArrowIcon, BriefcaseIcon, ShieldIcon, TrophyIcon } from "@/components/ui/Icons";
import { redirectIfSignedIn } from "@/lib/session";

const DOORS = [
  {
    href: "/login/organizer",
    icon: <TrophyIcon />,
    title: "Hackathon organizers",
    text: "Check every submission before judging starts: a score for each feature, red flags, and which teams built each feature best.",
    go: "Organizer sign-in",
  },
  {
    href: "/login/recruiter",
    icon: <BriefcaseIcon />,
    title: "Recruiters",
    text: "Turn a resume into a proof report: which projects really work, how they are built, and what the coding profiles show.",
    go: "Recruiter sign-in",
  },
];

const STEPS = [
  { title: "Read what the project claims", text: "From the demo video, your scoring criteria, or the resume and README." },
  {
    title: "Use it like a real person",
    text: "An agent signs up, clicks through and tries edge cases, saving a screenshot at every step.",
  },
  {
    title: "Get proof, not promises",
    text: "A score out of 10 for every feature, with a one-line reason and the evidence behind it.",
  },
];

// The promises in AGENTS.md section 1. They are product rules, not marketing: the scores are built to keep them.
const PROMISES = [
  { title: "Every number has proof", text: "Screenshots, steps, coverage and confidence sit next to each score." },
  { title: "Never blamed unfairly", text: "“Could not test” never counts against anyone and never means “fake”." },
  { title: "Flags beside the score", text: "Red flags are shown next to the score and are never subtracted from it." },
  { title: "Humans decide", text: "No winner picking and no ranking. TalNex gives you the evidence." },
];

export default async function Home() {
  await redirectIfSignedIn();

  return (
    <>
      <section className="hero">
        <div className="hero__glow" aria-hidden="true" />
        <div className="container">
          <span className="badge">For hackathon organizers and recruiters</span>
          <h1 className="hero__title">
            See what actually <span className="hero__mark">works</span>.
          </h1>
          <p className="hero__lead">
            A project link on a resume or a hackathon entry is a promise nobody has time to check. TalNex opens it like a
            real person would, and shows you the proof.
          </p>
          <div className="hero__actions">
            <Link className="button button--primary button--lg" href="/login">
              Get started <ArrowIcon />
            </Link>
            <a className="button button--ghost button--lg" href="#how">
              How it works
            </a>
          </div>
        </div>
      </section>

      <section className="section" aria-label="Who TalNex is for">
        <div className="container grid grid--2">
          {DOORS.map((door) => (
            <Link key={door.href} href={door.href} className="card card--soft card--link">
              <div className="card__icon">{door.icon}</div>
              <h2 className="card__title">{door.title}</h2>
              <p className="card__text">{door.text}</p>
              <span className="card__go">
                {door.go} <ArrowIcon size={16} />
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="section" id="how">
        <div className="container">
          <span className="section__eyebrow">How it works</span>
          <h2 className="section__title">Three steps, no checking by hand</h2>
          <ol className="section__body grid grid--3 plain-list">
            {STEPS.map((step, index) => (
              <li className="card" key={step.title}>
                <div className="step__num" aria-hidden="true">
                  {index + 1}
                </div>
                <h3 className="card__title">{step.title}</h3>
                <p className="card__text">{step.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <span className="section__eyebrow">
            <ShieldIcon size={16} /> Our promises
          </span>
          <h2 className="section__title">Built to be fair</h2>
          <div className="section__body grid grid--2">
            {PROMISES.map((promise) => (
              <div className="card" key={promise.title}>
                <h3 className="card__title">{promise.title}</h3>
                <p className="card__text">{promise.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
