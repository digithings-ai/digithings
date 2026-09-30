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
