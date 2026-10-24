// One question and its answer, read through the API, which checks the owner and adds short-lived screenshot links.
import { apiErrorResponse, apiFetch } from "@/lib/api";
import type { Walkthrough } from "@/lib/types";

export async function GET(_request: Request, { params }: { params: Promise<{ walkthroughId: string }> }) {
  const { walkthroughId } = await params;
  try {
    return Response.json(await apiFetch<Walkthrough>(`/v1/walkthroughs/${encodeURIComponent(walkthroughId)}`));
  } catch (error) {
    return apiErrorResponse(error);
  }
}
