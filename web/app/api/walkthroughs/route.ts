// "Ask about this feature": the browser sends its question here, and this server route passes it to the API with
// the signed token. The browser never holds a key and never touches storage.
import { apiErrorResponse, apiFetch } from "@/lib/api";
import type { Walkthrough } from "@/lib/types";
import { cleanQuestion, isSubject, walkthroughsPath } from "@/lib/walkthrough-format";

const UPLOAD_TIMEOUT_MS = 60_000;

/** Earlier questions about one project, newest first. */
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const subject = params.get("subject");
  const id = params.get("id") ?? "";
  if (!isSubject(subject) || !id) return Response.json({ error: "Unknown project." }, { status: 400 });
  try {
    return Response.json(await apiFetch<Walkthrough[]>(walkthroughsPath(subject, id)));
  } catch (error) {
    return apiErrorResponse(error);
  }
}

/** A new question: typed text, or a recording in the "audio" field. */
export async function POST(request: Request) {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return Response.json({ error: "The question did not arrive. Please try again." }, { status: 400 });
  }
  const subject = form.get("subject");
  const id = String(form.get("id") ?? "");
  if (!isSubject(subject) || !id) return Response.json({ error: "Unknown project." }, { status: 400 });

  const audio = form.get("audio");
  const question = cleanQuestion(form.get("question"));
  try {
    if (audio instanceof Blob && audio.size > 0) {
      const upload = new FormData();
      upload.set("audio", audio, audio instanceof File && audio.name ? audio.name : "question");
      const asked = await apiFetch(walkthroughsPath(subject, id), {
        method: "POST",
        form: upload,
        timeoutMs: UPLOAD_TIMEOUT_MS,
      });
      return Response.json(asked, { status: 202 });
    }
    if (!question) return Response.json({ error: "Please type or record a question." }, { status: 400 });
    return Response.json(await apiFetch(walkthroughsPath(subject, id), { method: "POST", body: { question } }), {
      status: 202,
    });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
