import { routeMap } from "@/lib/docs/content";

export async function GET() {
  return Response.json(routeMap());
}
