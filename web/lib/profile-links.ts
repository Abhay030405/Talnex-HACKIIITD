// The profile pages a resume can link to (ai/talnex_ai/resume/reader.py social_links_in), in the order they are shown.
// Links only: emails and phone numbers are never stored or shown.
export const PROFILE_KINDS = [
  { key: "github", label: "GitHub", example: "https://github.com/asha-dev" },
  { key: "linkedin", label: "LinkedIn", example: "https://www.linkedin.com/in/asha" },
  { key: "portfolio", label: "Portfolio", example: "https://asha.dev" },
  { key: "kaggle", label: "Kaggle", example: "https://www.kaggle.com/asha" },
  { key: "stackoverflow", label: "Stack Overflow", example: "https://stackoverflow.com/users/123" },
  { key: "medium", label: "Medium", example: "https://medium.com/@asha" },
  { key: "devto", label: "DEV", example: "https://dev.to/asha" },
  { key: "behance", label: "Behance", example: "https://www.behance.net/asha" },
  { key: "dribbble", label: "Dribbble", example: "https://dribbble.com/asha" },
  { key: "x", label: "X", example: "https://x.com/asha" },
  { key: "hackerrank", label: "HackerRank", example: "https://www.hackerrank.com/asha" },
  { key: "geeksforgeeks", label: "GeeksforGeeks", example: "https://www.geeksforgeeks.org/user/asha" },
] as const;

/** The links in display order: known kinds first, then any other kind, by name. */
export function orderedLinks(links: Record<string, string> | undefined): { key: string; label: string; url: string }[] {
  const all = links ?? {};
  const knownKeys = new Set<string>(PROFILE_KINDS.map((k) => k.key));
  const known = PROFILE_KINDS.filter((k) => all[k.key]).map((k) => ({ key: k.key, label: k.label, url: all[k.key] }));
  const other = Object.keys(all)
    .filter((k) => !knownKeys.has(k) && all[k])
    .sort()
    .map((k) => ({ key: k, label: k.charAt(0).toUpperCase() + k.slice(1), url: all[k] }));
  return [...known, ...other];
}

/** Profile link boxes from the confirm form (`link.<kind>`); an empty box removes that link. */
export function profileLinksFrom(form: FormData): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of PROFILE_KINDS) out[k.key] = String(form.get(`link.${k.key}`) ?? "").trim();
  return out;
}
