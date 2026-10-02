/**
 * Phase 4 — shell, settings, and chat.
 *
 * Desks and feature flags are the access catalog (no second policy).
 * Settings prefs and broker/key writes need the settings edge function:
 * reads are a typed empty state, writes are 503 not_provisioned.
 * Chat needs the digichat database, which this worker does not have:
 * reads are 502, create/rename/send are 503. Nothing is invented.
 */

import { DESKS } from "../access";
import { buildProvenance, errorResponse } from "../errors";
import { tableRows, type TableReadEnv } from "../table-read";
import type { RouteCtx, RouteModule } from "./registry";

type Env = TableReadEnv;

const SETTINGS_NOTE = "settings edge function is not configured";
const CHAT_NOTE = "digichat is not configured";
const NOT_PROVISIONED = "not provisioned";

function pinOf(req: Request): { pin: string | null } | { error: Response } {
  const pin = new URL(req.url).searchParams.get("retrieval_pin");
  if (pin !== null && pin.length > 128) {
    return { error: errorResponse("bad_request", "retrieval_pin exceeds 128 characters", null, { max_length: 128 }) };
  }
  return { pin };
}

function ok(data: unknown, source: string, pin: string | null, asOf: string | null = null): Response {
  return Response.json({
    data,
    as_of: asOf,
    retrieval_pin: pin,
    provenance: buildProvenance({ source, tip_date: asOf, marks: "unavailable" }),
  });
}

function notProvisioned(pin: string | null, what: string): Response {
  return Response.json(
    { error: { code: "not_provisioned", message: `${what} is ${NOT_PROVISIONED}`, details: { what }, retrieval_pin: pin } },
    { status: 503 },
  );
}

function chatClosed(pin: string | null): Response {
  return errorResponse("upstream_empty", CHAT_NOTE, pin, { source: "digichat" });
}

function desks(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok(
    {
      desks: DESKS.map((d) => ({
        id: d.id,
        name: d.label,
        chip: d.group ?? null,
        note: d.blurb,
        spine: d.pages.map((p) => p.path),
        active: null,
      })),
      hint: "The active desk is chosen in the app. This route does not store one.",
    },
    "access_policy",
    pinR.pin,
  );
}

function spine(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const baseline = DESKS.find((d) => d.id === "baseline");
  return ok(
    {
      desk_id: baseline?.id ?? null,
      items: (baseline?.pages ?? []).map((p, i) => ({
        no: String(i + 1).padStart(2, "0"),
        label: p.label,
        href: p.path,
      })),
    },
    "access_policy",
    pinR.pin,
  );
}

function features(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const flags: { key: string; tag: "wip" | "soon"; text: string; action: { label: string; href: string } }[] = [];
  for (const d of DESKS) {
    for (const p of d.pages) {
      if (!p.status) continue;
      flags.push({ key: p.path, tag: p.status, text: p.label, action: { label: "open", href: p.path } });
    }
  }
  return ok({ flags }, "access_policy", pinR.pin);
}

function prefs(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok(
    {
      display_name: null,
      email: null,
      density: null,
      density_options: null,
      daily_digest: null,
      research_notices: null,
      note: SETTINGS_NOTE,
    },
    "edge:settings",
    pinR.pin,
  );
}

function settingsDesk(req: Request, ctx: RouteCtx<Env>): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok(
    {
      plan: null,
      config: null,
      config_note: SETTINGS_NOTE,
      book_date: null,
      posture: null,
      tags: ctx.caller.groups.length > 0 ? ctx.caller.groups : null,
    },
    "edge:settings",
    pinR.pin,
  );
}

function fxFeed(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok(
    {
      grant: null,
      posture: null,
      feed: null,
      keys: [],
      generation: { mode: null, note: SETTINGS_NOTE },
    },
    "edge:settings",
    pinR.pin,
  );
}

function brokers(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok({ brokers: [], connectable: null, note: SETTINGS_NOTE }, "edge:settings", pinR.pin);
}

function brokerConnectGet(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok({ status: null, detail: SETTINGS_NOTE, auth_url: null }, "edge:settings", pinR.pin);
}

function integrations(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok({ integrations: [], note: SETTINGS_NOTE }, "edge:settings", pinR.pin);
}

function keys(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok({ keys: [], note: SETTINGS_NOTE }, "edge:settings", pinR.pin);
}

function keyOne(req: Request, ctx: RouteCtx<Env>): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return errorResponse("upstream_empty", SETTINGS_NOTE, pinR.pin, { id: ctx.params.id ?? null });
}

async function latestRun(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const out = await tableRows(ctx.env, {
    table: "run_health",
    query: "select=run_date,status,finished_at,duration_s&order=run_date.desc&limit=1",
    allowEmpty: true,
  });
  if ("error" in out) return out.error;
  const row = out.rows[0];
  const runDate = typeof row?.run_date === "string" ? row.run_date.slice(0, 10) : null;
  const duration = typeof row?.duration_s === "number" && Number.isFinite(row.duration_s) ? row.duration_s : null;
  return Response.json({
    data: {
      run_date: runDate,
      status: typeof row?.status === "string" ? row.status : null,
      finished_at: typeof row?.finished_at === "string" ? row.finished_at : null,
      duration_s: duration,
    },
    as_of: runDate,
    retrieval_pin: pinR.pin,
    provenance: buildProvenance({ source: "core:run_health", tip_date: runDate, marks: row ? "stored" : "unavailable" }),
  });
}

function writePin(req: Request): string | null {
  const pin = new URL(req.url).searchParams.get("retrieval_pin");
  return pin !== null && pin.length > 128 ? null : pin;
}

export const registerDesk: RouteModule<Env> = (reg) => {
  reg.get("/desks", async (req) => desks(req));
  reg.get("/desks/active/spine", async (req) => spine(req));
  reg.get("/features", async (req) => features(req));
  reg.get("/settings/prefs", async (req) => prefs(req));
  reg.add("PUT", "/settings/prefs", async (req) => notProvisioned(writePin(req), "settings prefs"));
  reg.get("/settings/desk", async (req, ctx) => settingsDesk(req, ctx));
  reg.get("/settings/fx-feed", async (req) => fxFeed(req));
  reg.get("/settings/brokers", async (req) => brokers(req));
  reg.get("/settings/brokers/connect", async (req) => brokerConnectGet(req));
  reg.add("POST", "/settings/brokers/connect", async (req) => notProvisioned(writePin(req), "broker connect"));
  reg.get("/settings/integrations", async (req) => integrations(req));
  reg.get("/settings/keys", async (req) => keys(req));
  reg.add("POST", "/settings/keys", async (req) => notProvisioned(writePin(req), "key mint"));
  reg.get("/settings/keys/{id}", async (req, ctx) => keyOne(req, ctx));
  reg.add("DELETE", "/settings/keys/{id}", async (req) => notProvisioned(writePin(req), "key revoke"));
  reg.get("/pipeline/runs/latest", latestRun);
  reg.get("/chat/sessions", async (req) => {
    const pinR = pinOf(req);
    return "error" in pinR ? pinR.error : chatClosed(pinR.pin);
  });
  reg.get("/chat/sessions/current", async (req) => {
    const pinR = pinOf(req);
    return "error" in pinR ? pinR.error : chatClosed(pinR.pin);
  });
  reg.get("/chat/sessions/current/messages", async (req) => {
    const pinR = pinOf(req);
    return "error" in pinR ? pinR.error : chatClosed(pinR.pin);
  });
  reg.get("/chat/sessions/{id}", async (req) => {
    const pinR = pinOf(req);
    return "error" in pinR ? pinR.error : chatClosed(pinR.pin);
  });
  reg.get("/chat/sessions/{id}/messages", async (req) => {
    const pinR = pinOf(req);
    return "error" in pinR ? pinR.error : chatClosed(pinR.pin);
  });
  reg.add("POST", "/chat/sessions", async (req) => notProvisioned(writePin(req), "chat session create"));
  reg.add("PUT", "/chat/sessions/{id}", async (req) => notProvisioned(writePin(req), "chat session rename"));
  reg.add("POST", "/chat/sessions/{id}/messages", async (req) => notProvisioned(writePin(req), "chat send"));
};
