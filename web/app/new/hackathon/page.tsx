import type { Metadata } from "next";

import { FormAside } from "@/components/forms/FormAside";
import { HackathonForm } from "@/components/forms/HackathonForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { requireRole } from "@/lib/session";

export const metadata: Metadata = { title: "New hackathon check" };

const STEPS = [
  "Save the event with its dates, type and role level.",
  "Add each team's live site, repository and demo video.",
  "TalNex uses every live project like a real person and saves a screenshot at every step.",
  "You read the proof cards. Humans decide; there is no ranking.",
];

const NOTES = [
  "Code pushed before the start date is flagged, never subtracted from a score.",
  "Sponsor tools are optional. They let TalNex check that a team really used them.",
  "Test data is labelled “TalNex test”. Nothing is paid, deleted or sent to real users.",
  "“Could not test” never counts against a team.",
];

export default async function NewHackathonPage() {
  await requireRole("organizer");

  return (
    <div className="stack">
      <PageHeader
        title="New hackathon check"
        lead="Tell TalNex about the event. You add the teams next."
        back={{ href: "/organizer", label: "All events" }}
      />
      <div className="form-layout">
        <div className="card">
          <HackathonForm />
        </div>
        <FormAside steps={STEPS} notes={NOTES} />
      </div>
    </div>
  );
}
