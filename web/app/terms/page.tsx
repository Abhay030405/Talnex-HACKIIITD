import type { Metadata } from "next";
import Link from "next/link";

import { DocPage, type DocSection } from "@/components/ui/DocPage";

export const metadata: Metadata = { title: "Terms of use" };

// Written from what the product actually does (AGENTS.md sections 1 and 8). Change this page when that changes.
const SECTIONS: DocSection[] = [
  {
    id: "service",
    title: "What TalNex is",
    body: (
      <p>
        TalNex is a service for hackathon organizers and recruiters. Its AI agent opens a project’s live link, uses it
        the way a person would, saves a screenshot at every step and reports what works. Results are evidence to help
        you decide. They are not a decision.
      </p>
    ),
  },
  {
    id: "account",
    title: "Your account",
    body: (
      <ul>
        <li>Each email address belongs to one kind of account: organizer or recruiter.</li>
        <li>Keep your sign-in safe. You are responsible for checks started from your account.</li>
        <li>You must be old enough to agree to these terms where you live.</li>
      </ul>
    ),
  },
  {
    id: "submit",
    title: "What you may submit",
    body: (
      <>
        <p>Only submit projects, links and files you have the right to share with us. In particular:</p>
        <ul>
          <li>Organizers should tell participants that their submissions will be checked by TalNex.</li>
          <li>Recruiters need the candidate’s permission, or another lawful reason, to upload a resume.</li>
          <li>Do not submit sites you are not allowed to test, or use TalNex to attack, overload or scrape a site.</li>
        </ul>
      </>
    ),
  },
  {
    id: "testing",
    title: "How we behave on tested sites",
    body: (
      <ul>
        <li>The agent never pays, deletes anything or messages real users.</li>
        <li>Everything it creates is labelled “TalNex test”.</li>
        <li>It stops after 3 tries per claim and 30 runs per project.</li>
        <li>It follows a site’s rules for automated visitors where they apply.</li>
      </ul>
    ),
  },
  {
    id: "results",
    title: "How to read results",
    body: (
      <>
        <p>
          A score reflects what happened on screen during the check. Sites change, so a later visit may differ. “Could
          not test” never means a project is fake or broken, and it never lowers a score.
        </p>
        <p>
          Flags, such as code written before an event, are shown for a person to judge. The “AI opinion” on design and
          originality is labelled as opinion and is never part of the score. TalNex does not rank people or pick
          winners. You do.
        </p>
      </>
    ),
  },
  {
    id: "wrong",
    title: "When a result looks wrong",
    body: (
      <p>
        Tell us through the <Link href="/contact">contact page</Link> with the project and the claim. A person reviews
        the screenshots and replies. Please do not rely on a single result alone for a decision that matters to someone.
      </p>
    ),
  },
  {
    id: "limits",
    title: "Limits of the service",
    body: (
      <p>
        We work hard to make results accurate and fair, but the service is provided as it is, without a promise that it
        is free of mistakes or always available. As far as the law allows, we are not responsible for decisions made
        using TalNex results.
      </p>
    ),
  },
  {
    id: "ending",
    title: "Ending your use",
    body: (
      <p>
        You can stop using TalNex and ask us to delete your account at any time. We may suspend an account that breaks
        these terms, and will tell you why.
      </p>
    ),
  },
  {
    id: "changes",
    title: "Changes to these terms",
    body: (
      <p>
        When something important changes, we update this page and the date at the top, and tell signed-in users before
        it takes effect. Our <Link href="/privacy">privacy policy</Link> explains how we handle data.
      </p>
    ),
  },
];

export default function TermsPage() {
  return (
    <DocPage
      title="Terms of use"
      lead="The agreement between you and TalNex, in plain words."
      updated="25 October 2026"
      sections={SECTIONS}
    />
  );
}
