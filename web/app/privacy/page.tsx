import type { Metadata } from "next";
import Link from "next/link";

import { DocPage, type DocSection } from "@/components/ui/DocPage";

export const metadata: Metadata = { title: "Privacy policy" };

// Written from what the product actually does (AGENTS.md sections 1, 5 and 8). Change this page when that changes.
const SECTIONS: DocSection[] = [
  {
    id: "summary",
    title: "The short version",
    body: (
      <ul>
        <li>Results belong to the person who started the check. Nobody else can see them.</li>
        <li>Resume files and personal details are deleted once the report is made. Only the results stay.</li>
        <li>We do not sell data and we do not use it for advertising.</li>
        <li>You can ask what we hold about you, or ask us to delete it, at any time.</li>
      </ul>
    ),
  },
  {
    id: "collect",
    title: "What we collect",
    body: (
      <>
        <p>
          <strong>Your account.</strong> Your name and email address from Google sign-in, and whether you signed in as
          an organizer or a recruiter.
        </p>
        <p>
          <strong>What you give us to check.</strong> For hackathons: event details, team names, live links, repository
          links and demo videos. For hiring: the resume you upload and the project links you confirm.
        </p>
        <p>
          <strong>What a check produces.</strong> Screenshots of each step, the steps taken, scores, flags and the
          report. Recordings of public coding profiles, when a recruiter asks for them.
        </p>
        <p>
          <strong>Cookies.</strong> One cookie keeps you signed in and one remembers which sign-in you chose. We use no
          advertising or tracking cookies.
        </p>
      </>
    ),
  },
  {
    id: "use",
    title: "How we use it",
    body: (
      <ul>
        <li>To run the checks you ask for and show you the results.</li>
        <li>To keep the service working and safe, for example to stop misuse.</li>
        <li>To answer you when you write to us.</li>
      </ul>
    ),
  },
  {
    id: "resumes",
    title: "Resumes and candidate details",
    body: (
      <>
        <p>
          A resume is read only to find the projects and coding profiles it mentions. Under India’s Digital Personal
          Data Protection Act, 2023, the resume file and the candidate’s personal details are deleted once the proof
          report is made. The results stay with the recruiter who asked for them.
        </p>
        <p>Recruiters must have the candidate’s permission, or another lawful reason, to upload a resume.</p>
      </>
    ),
  },
  {
    id: "share",
    title: "Who else handles data",
    body: (
      <>
        <p>We use a few services to do the work. Each sees only what it needs:</p>
        <ul>
          <li>An AI web agent and browser service that opens the live sites being tested.</li>
          <li>AI model providers that read claims and screenshots and help score them.</li>
          <li>Cloud file storage for screenshots, videos and resume files, shared only through short-lived links.</li>
          <li>GitHub and Codeforces, through their official public APIs.</li>
          <li>Throwaway test inboxes, used when a tested site needs an email to sign up.</li>
        </ul>
        <p>We never put the logins we use for testing in our database.</p>
      </>
    ),
  },
  {
    id: "keep",
    title: "How long we keep it",
    body: (
      <p>
        Resume files and candidate details: until the report is made. Results and screenshots: for as long as your
        account is open, or until you delete them. When you close your account, we delete what belongs to it.
      </p>
    ),
  },
  {
    id: "rights",
    title: "Your rights",
    body: (
      <p>
        You can ask to see the personal data we hold about you, correct it, or have it deleted. Candidates can ask too,
        even if they never used TalNex themselves. Write to us through the <Link href="/contact">contact page</Link> and
        we will reply within 7 days.
      </p>
    ),
  },
  {
    id: "changes",
    title: "Changes to this policy",
    body: (
      <p>
        When something important changes, we update this page and the date at the top, and tell signed-in users before
        it takes effect.
      </p>
    ),
  },
];

export default function PrivacyPage() {
  return (
    <DocPage
      title="Privacy policy"
      lead="What TalNex collects, why, and how long it keeps it. Written to be read in five minutes."
      updated="25 October 2026"
      sections={SECTIONS}
    />
  );
}
