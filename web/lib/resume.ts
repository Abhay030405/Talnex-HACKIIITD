// The resume file rules, the same as the API's (backend/internal/http/resume.go): a real PDF of at most 5 MB.
// Checked before anything is saved, so a wrong file never leaves an empty candidate behind.

export const MAX_RESUME_BYTES = 5 * 1024 * 1024;
/** The recruiter's own name for a candidate in their list. */
export const MAX_LABEL_LENGTH = 120;

/** What is wrong with the chosen file, in words, or null when the API will take it. */
export async function resumeProblem(file: FormDataEntryValue | null): Promise<string | null> {
  if (!(file instanceof Blob) || file.size === 0) return "Please choose the resume as a PDF file.";
  if (file.size > MAX_RESUME_BYTES) return "The resume file is larger than 5 MB.";
  // The API looks at what the file is, not what it is called: every PDF starts with "%PDF-".
  const start = new TextDecoder().decode(await file.slice(0, 5).arrayBuffer());
  if (start !== "%PDF-") return "The resume must be a PDF file. Save it as PDF and try again.";
  return null;
}
