// Docker Compose asks this before it starts anything that waits for the website.
export function GET() {
  return Response.json({ status: "ok" });
}
