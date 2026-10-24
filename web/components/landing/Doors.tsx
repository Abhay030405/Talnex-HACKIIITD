import { ButtonLink } from "@/components/ui/Button";

const DOORS = [
  {
    title: "For hackathon organizers",
    text: "Add each team's live site, repository and demo video. Before judging starts you have a proof card per team, code written before the event flagged, and the teams that built each feature best.",
    href: "/login/organizer",
    go: "Sign in as an organizer",
  },
  {
    title: "For recruiters",
    text: "Upload a resume and confirm the projects TalNex finds. You get a proof report for the interview: what really works, who wrote the code, and what the coding profiles suggest.",
    href: "/login/recruiter",
    go: "Sign in as a recruiter",
  },
];

export function Doors() {
  return (
    <section className="doors-split wrap" aria-label="Who TalNex is for">
      {DOORS.map((door) => (
        <div key={door.href} className="doors-split__col">
          <h2 className="doors-split__title">{door.title}</h2>
          <p className="doors-split__text">{door.text}</p>
          <ButtonLink href={door.href} variant="secondary">
            {door.go}
          </ButtonLink>
        </div>
      ))}
    </section>
  );
}

export function Closing() {
  return (
    <section className="closing wrap" aria-labelledby="closing-title">
      <h2 className="closing__title" id="closing-title">
        Stop grading the demo video.
      </h2>
      <div className="closing__side">
        <p>Your first proof card takes about five minutes.</p>
        <ButtonLink href="/login" variant="primary" size="lg">
          Check a project
        </ButtonLink>
      </div>
    </section>
  );
}
