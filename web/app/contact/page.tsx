import { Mail } from "lucide-react";
import type { Metadata } from "next";

import { PageHero } from "@/components/ui/PageHero";
import { env } from "@/lib/env";

export const metadata: Metadata = { title: "Contact" };

// The address comes from the running server's settings, so read it on each request rather than at build time.
export const dynamic = "force-dynamic";

// What to put in the message, so one email is enough to act on.
const TOPICS = [
  {
    title: "Running a hackathon",
    text: "Tell us the event dates, how many teams, and whether it is open theme or a fixed problem.",
    subject: "Hackathon checks",
  },
  {
    title: "Hiring",
    text: "Tell us roughly how many candidates a month and the roles you hire for.",
    subject: "Recruiter checks",
  },
  {
    title: "A result looks wrong",
    text: "Send the project name and the claim. A person looks at the screenshots and replies with what they found.",
    subject: "Result review",
  },
  {
    title: "Your data",
    text: "Ask what we hold about you, or ask us to delete it. We reply within 7 days.",
    subject: "Data request",
  },
];

export default function ContactPage() {
  const email = env.contactEmail;

  return (
    <>
      <PageHero
        title="Talk to us"
        lead="Questions, a check that looks wrong, or a request about your data: one email reaches the team."
      />

      <section className="contact wrap" aria-label="Ways to reach us">
        <div className="contact__main">
          {email ? (
            <a className="contact__email" href={`mailto:${email}`}>
              <Mail size={28} strokeWidth={1.75} aria-hidden="true" />
              {email}
            </a>
          ) : (
            <p className="contact__missing">
              The contact address is not set up yet. Set CONTACT_EMAIL in the website settings to show it here.
            </p>
          )}
          <p className="contact__note">We usually answer within two working days.</p>
        </div>

        <ul className="contact__topics">
          {TOPICS.map((topic) => (
            <li key={topic.title} className="contact__topic">
              <h2 className="contact__title">{topic.title}</h2>
              <p className="contact__text">{topic.text}</p>
              {email && (
                <a className="text-link" href={`mailto:${email}?subject=${encodeURIComponent(topic.subject)}`}>
                  Email about this
                </a>
              )}
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
