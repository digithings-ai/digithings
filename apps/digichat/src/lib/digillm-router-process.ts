/**
 * Run digillm's router as a library process.
 *
 * `python -m digillm.router` reads one JSON request and writes one decision.
 * It does not call a provider. Tests inject `run` so this file's default
 * spawn is never required on the chat-route suite, and nothing here knows a
 * paid inference URL.
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

import {
  type DigillmRouterDecision,
  type DigillmRouterRouteInput,
} from "@/lib/digillm-router";

const STDOUT_LIMIT = 8_192;
const TIMEOUT_MS = 8_000;

export class DigillmRouterUnavailable extends Error {
  constructor() {
    super("digillm router unavailable");
    this.name = "DigillmRouterUnavailable";
  }
}

export type DigillmRouterRunInput = {
  text: string;
  allowed: readonly string[];
  fallback: string;
  routes?: readonly DigillmRouterRouteInput[];
};

export type DigillmRouterRunner = (
  input: DigillmRouterRunInput,
) => Promise<DigillmRouterDecision>;

function digillmSrcOnPath(): string | undefined {
  let dir = process.cwd();
  for (let hop = 0; hop < 5; hop += 1) {
    const candidate = path.join(dir, "digillm", "src");
    if (existsSync(path.join(candidate, "digillm", "router", "__main__.py"))) {
      return candidate;
    }
    const parent = path.dirname(dir);
    if (parent === dir) return undefined;
    dir = parent;
  }
  return undefined;
}

function pythonEnv(): NodeJS.ProcessEnv {
  const env = { ...process.env };
  const src = digillmSrcOnPath();
  if (src) {
    env.PYTHONPATH = env.PYTHONPATH ? `${src}${path.delimiter}${env.PYTHONPATH}` : src;
  }
  return env;
}

function readDecision(stdout: string): DigillmRouterDecision {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout) as unknown;
  } catch {
    throw new DigillmRouterUnavailable();
  }
  if (!parsed || typeof parsed !== "object") throw new DigillmRouterUnavailable();
  const record = parsed as Record<string, unknown>;
  if (record.error) throw new DigillmRouterUnavailable();
  const routeId = record.route_id;
  const label = record.label;
  const model = record.model;
  const reason = record.reason;
  const confidence = record.confidence;
  if (
    typeof routeId !== "string" ||
    typeof label !== "string" ||
    typeof model !== "string" ||
    typeof reason !== "string" ||
    typeof confidence !== "number" ||
    !routeId ||
    !label ||
    !model ||
    !reason
  ) {
    throw new DigillmRouterUnavailable();
  }
  return { routeId, label, model, reason, confidence };
}

/** Default runner. One short-lived interpreter, then the process is gone. */
export const spawnDigillmRouter: DigillmRouterRunner = (input) =>
  new Promise((resolve, reject) => {
    const child = spawn(
      process.env.DIGILLM_PYTHON?.trim() || "python3",
      ["-m", "digillm.router"],
      { env: pythonEnv(), stdio: ["pipe", "pipe", "pipe"] },
    );
    let stdout = "";
    let settled = false;
    const finish = (error?: Error, decision?: DigillmRouterDecision) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) reject(error);
      else if (decision) resolve(decision);
      else reject(new DigillmRouterUnavailable());
    };
    const timer = setTimeout(() => {
      child.kill();
      finish(new DigillmRouterUnavailable());
    }, TIMEOUT_MS);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      stdout += chunk;
      if (stdout.length > STDOUT_LIMIT) {
        child.kill();
        finish(new DigillmRouterUnavailable());
      }
    });
    child.on("error", () => finish(new DigillmRouterUnavailable()));
    child.on("close", (code) => {
      if (code !== 0) {
        finish(new DigillmRouterUnavailable());
        return;
      }
      try {
        finish(undefined, readDecision(stdout));
      } catch (error) {
        finish(error instanceof Error ? error : new DigillmRouterUnavailable());
      }
    });
    child.stdin.write(
      JSON.stringify({
        text: input.text,
        allowed: [...input.allowed],
        fallback: input.fallback,
        ...(input.routes ? { routes: input.routes } : {}),
      }),
    );
    child.stdin.end();
  });

let runner: DigillmRouterRunner = spawnDigillmRouter;

export function setDigillmRouterRunnerForTests(next: DigillmRouterRunner | null): void {
  runner = next ?? spawnDigillmRouter;
}

export function routeWithDigillm(input: DigillmRouterRunInput): Promise<DigillmRouterDecision> {
  return runner(input);
}
