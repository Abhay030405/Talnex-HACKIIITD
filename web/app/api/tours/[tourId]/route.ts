// One tour chat: read it (the page asks while the guide works) and add a question to it. Passed to the API with the
// signed token; the browser never holds a key.
import { apiErrorResponse, apiFetch } from "@/lib/api";
import { cleanTourQuestion, isTourId, tourMessagesPath, tourPath, type Tour } from "@/lib/tour";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ tourId: string }> }) {
  const { tourId } = await params;
  if (!isTourId(tourId)) return Response.json({ error: "Tour not found." }, { status: 404 });
  try {
    return Response.json(await apiFetch<Tour>(tourPath(tourId)));
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function POST(request: Request, { params }: { params: Promise<{ tourId: string }> }) {
  const { tourId } = await params;
  if (!isTourId(tourId)) return Response.json({ error: "Tour not found." }, { status: 404 });
  let body: { question?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "The question did not arrive. Please try again." }, { status: 400 });
  }
  const question = cleanTourQuestion(body.question);
  if (!question) return Response.json({ error: "Please type a question." }, { status: 400 });
  try {
    return Response.json(await apiFetch(tourMessagesPath(tourId), { method: "POST", body: { question } }), { status: 202 });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
