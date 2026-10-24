import type { Metadata } from "next";

import { FormAside } from "@/components/forms/FormAside";
import { RecruiterForm } from "@/components/forms/RecruiterForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { requireRole } from "@/lib/session";

export const metadata: Metadata = { title: "New recruiter check" };

const STEPS = [
  "Upload the resume and pick the role level.",
  "TalNex reads the projects, their links and the coding profiles on it.",
  "You check what was found, fix or add anything, and start the checks.",
  "TalNex uses each live project like a real person. You get a proof report: a score out of 10 per feature, with the evidence.",
];

const NOTES = [
  "The candidate is never contacted.",
  "The resume file is deleted after the report is made. Only the results stay.",
  "Nothing is tested until you confirm what was found.",
  "TalNex does not check that a coding profile belongs to the candidate.",
  "“Could not test” never counts against the candidate.",
];

export default async function NewRecruiterPage() {
  await requireRole("recruiter");

  return (
    <div className="stack">
      <PageHeader
        title="New recruiter check"
        lead="Upload the resume and pick the role level, so features are judged fairly."
        back={{ href: "/recruiter", label: "All candidates" }}
      />
      <div className="form-layout">
        <div className="card">
          <RecruiterForm />
        </div>
        <FormAside steps={STEPS} notes={NOTES} />
      </div>
    </div>
  );
}
