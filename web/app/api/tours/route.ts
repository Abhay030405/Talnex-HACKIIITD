// Starts a guided tour chat. The browser sends the project and the first question here; this server route passes them to
// the API with the signed token. The browser never holds a key.
import { apiErrorResponse, apiFetch } from "@/lib/api";
import { cleanTourQuestion, isSubject, tourStartPath } from "@/lib/tour";

export async function POST(request: Request) {
  let body: { subject?: unknown; id?: unknown; question?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "The question did not arrive. Please try again." }, { status: 400 });
  }
  const id = typeof body.id === "string" ? body.id : "";
  if (!isSubject(body.subject) || !id) return Response.json({ error: "Unknown project." }, { status: 400 });
  const question = cleanTourQuestion(body.question);
  if (!question) return Response.json({ error: "Please type a question." }, { status: 400 });
  try {
    return Response.json(await apiFetch(tourStartPath(body.subject, id), { method: "POST", body: { question } }), {
      status: 202,
    });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
