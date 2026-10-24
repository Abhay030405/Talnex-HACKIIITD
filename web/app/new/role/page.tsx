import type { Metadata } from "next";

import { FormAside } from "@/components/forms/FormAside";
import { RoleForm } from "@/components/forms/RoleForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { requireRole } from "@/lib/session";

export const metadata: Metadata = { title: "New role" };

const STEPS = [
  "Describe the role: the job description, the kind of person, must-have skills and how to weigh what you care about.",
  "Upload one resume or a whole batch.",
  "TalNex reads each resume and starts its checks. Results appear as they come in.",
  "Every candidate gets a proof report judged against this role, with an interview kit.",
];

const NOTES = [
  "Candidates are never contacted.",
  "Resume files are deleted after each report. Only the results stay.",
  "“Could not test” never counts against a candidate.",
  "There is no ranking of candidates. You decide.",
];

export default async function NewRolePage() {
  await requireRole("recruiter");
  return (
    <div className="stack">
      <PageHeader
        title="New role"
        lead="Tell TalNex what you are hiring for, then upload the resumes."
        back={{ href: "/recruiter", label: "All candidates" }}
      />
      <div className="form-layout">
        <div className="card">
          <RoleForm />
        </div>
        <FormAside steps={STEPS} notes={NOTES} />
      </div>
    </div>
  );
}
