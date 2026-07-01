import { cookies } from "next/headers";
import { auth } from "@/auth";
import {
  ENDPOINTS_COOKIE,
  getEcosystemDefaults,
  getEcosystemEndpoints,
  parseEndpointsPayload,
  withDigisearchCapability,
} from "@/lib/ecosystem";

const COOKIE_MAX_AGE = 60 * 60 * 24 * 180; // 180 days

export async function GET() {
  const session = await auth();
  if (!session?.user) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  const jar = await cookies();
  const hasCustom = Boolean(jar.get(ENDPOINTS_COOKIE)?.value);
  const effective = await getEcosystemEndpoints();
  const defaults = getEcosystemDefaults();
  const persistence = {
    serverDatabaseConfigured: Boolean(process.env.DIGICHAT_DATABASE_URL?.trim()),
  };

  return Response.json({
    effective,
    defaults,
    hasCustomEndpoints: hasCustom,
    persistence,
  });
}

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid_json" }, { status: 400 });
  }
  const jar = await cookies();
  const isProd = process.env.NODE_ENV === "production";

  if (body && typeof body === "object" && "reset" in body && (body as { reset?: boolean }).reset) {
    jar.delete(ENDPOINTS_COOKIE);
    const effective = await getEcosystemEndpoints();
    return Response.json({ ok: true, effective, reset: true });
  }

  const parsed = parseEndpointsPayload(body);
  if (!parsed) {
    return Response.json(
      {
        error: "invalid_endpoints",
        message:
          "Three valid http(s) URLs required (DigiGraph, DigiQuant, DigiSmith). Optional fourth: digisearchUrl (DigiSearch / RAG).",
      },
      { status: 400 }
    );
  }

  const effectiveSaved = withDigisearchCapability(parsed);

  jar.set(ENDPOINTS_COOKIE, JSON.stringify(effectiveSaved), {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: COOKIE_MAX_AGE,
    secure: isProd,
  });

  return Response.json({ ok: true, effective: effectiveSaved });
}
