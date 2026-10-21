import { getNeonAuthServer } from "@/lib/auth/server";

type Ctx = { params: Promise<{ path: string[] }> };

function notConfigured() {
  return Response.json(
    { code: "AUTH_NOT_CONFIGURED", detail: "Neon Auth is not configured on this deployment." },
    { status: 404 },
  );
}

async function forward(method: "GET" | "POST", request: Request, ctx: Ctx) {
  const auth = await getNeonAuthServer();
  if (!auth) return notConfigured();
  return auth.handler()[method](request, ctx);
}

export const GET = (request: Request, ctx: Ctx) => forward("GET", request, ctx);
export const POST = (request: Request, ctx: Ctx) => forward("POST", request, ctx);
