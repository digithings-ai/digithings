/**
 * digiquant-runner — private Worker in front of one batch container (issue #4761).
 * No public hostname. digithings-cron calls it over the RUNNER service binding.
 */
import { getContainer } from "@cloudflare/containers";
import { assertKnownCommand } from "./commands";
import type { Env } from "./env";
import { COMMANDS } from "./runner-session";
import { DigiQuantRunnerContainer, RUNNER_CONTAINER_ID } from "./runner";

export { DigiQuantRunnerContainer };

function normalizePath(pathname: string): string {
  if (pathname.length > 1 && pathname.endsWith("/")) return pathname.slice(0, -1);
  return pathname || "/";
}

function authorized(request: Request, env: Env): boolean {
  const token = env.RUNNER_AUTH_TOKEN;
  if (!token) return false;
  return (request.headers.get("Authorization") ?? "") === `Bearer ${token}`;
}

function argsOf(parsed: unknown): Record<string, unknown> {
  if (typeof parsed !== "object" || parsed === null || !("args" in parsed)) return {};
  const args = (parsed as { args?: unknown }).args;
  if (typeof args !== "object" || args === null || Array.isArray(args)) return {};
  return args as Record<string, unknown>;
}

/** Skip before getContainer so a finished UTC day does not cold-start. */
async function houseRunGate(parsed: unknown, env: Env): Promise<Response | null> {
  if (!env.ARCHIVE) {
    return Response.json({ error: "house_ledger_unconfigured" }, { status: 500 });
  }
  const args = argsOf(parsed);
  if (args.force === "true") return null;
  const runDate = args.run_date;
  if (typeof runDate !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(runDate)) return null;
  const key = `pipeline-runs/house-run/${runDate}/success.json`;
  let hit: unknown;
  try {
    hit = await env.ARCHIVE.head(key);
  } catch {
    return Response.json({ error: "house_ledger_read_failed" }, { status: 500 });
  }
  if (!hit) return null;
  let runId = "";
  try {
    const object = await env.ARCHIVE.get(key);
    if (object) {
      const text = await object.text();
      const body = JSON.parse(text) as unknown;
      if (typeof body === "object" && body !== null && "run_id" in body) {
        const value = (body as { run_id?: unknown }).run_id;
        if (typeof value === "string") runId = value;
      }
    }
  } catch {
    runId = "";
  }
  console.log("skipped: house_already_succeeded");
  return Response.json({ ok: true, run_id: runId, status: "skipped" }, { status: 202 });
}

function stub(env: Env): Fetcher {
  const binding = env.RUNNER_CONTAINER as unknown as DurableObjectNamespace<DigiQuantRunnerContainer>;
  return getContainer(binding, RUNNER_CONTAINER_ID);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const path = normalizePath(new URL(request.url).pathname);

    if (request.method === "GET" && path === "/healthz") {
      return stub(env).fetch(request);
    }

    if (!path.startsWith("/v1/jobs")) {
      return new Response("Not Found", { status: 404 });
    }
    if (!authorized(request, env)) {
      return new Response("Unauthorized", { status: 401 });
    }

    if (request.method === "POST" && path === "/v1/jobs") {
      const raw = await request.text();
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        return Response.json({ error: "invalid_json" }, { status: 400 });
      }
      const command =
        typeof parsed === "object" && parsed !== null && "command" in parsed
          ? (parsed as { command?: unknown }).command
          : undefined;
      if (typeof command !== "string") {
        return Response.json({ error: "invalid_body" }, { status: 400 });
      }
      try {
        assertKnownCommand(command, COMMANDS);
      } catch (err) {
        const message = err instanceof Error ? err.message : "unknown command";
        return Response.json({ error: message }, { status: 400 });
      }
      if (command === "house-run") {
        const gated = await houseRunGate(parsed, env);
        if (gated) return gated;
      }
      return stub(env).fetch(
        new Request(request.url, { method: "POST", headers: request.headers, body: raw }),
      );
    }

    if (request.method === "GET") {
      return stub(env).fetch(request);
    }
    return new Response("Not Found", { status: 404 });
  },
};
