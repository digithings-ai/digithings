/**
 * Arguments for `scripts/export-replay.ts`. The script is the thin part;
 * this parser is what the tests pin.
 */

export type ReplayCliPlan =
  | { mode: "fixture"; out: string | null }
  | {
      mode: "conversation";
      id: string;
      out: string | null;
      baseUrl: string;
      authorization: string | null;
      theme: string | null;
      palette: string | null;
      view: string | null;
    };

export type ReplayCliResult = { ok: true; plan: ReplayCliPlan } | { ok: false; message: string };

export function parseReplayCli(
  argv: readonly string[],
  env: Record<string, string | undefined>,
): ReplayCliResult {
  let fixture = false;
  let id = "";
  let out: string | null = null;
  let base = env.DIGICHAT_URL?.trim() || "http://127.0.0.1:3000";
  let authorization = env.DIGICHAT_REPLAY_AUTHORIZATION?.trim() || "";
  let theme: string | null = null;
  let palette: string | null = null;
  let view: string | null = null;

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i] ?? "";
    const [flag, inline] = splitFlag(token);
    const next = () => {
      if (inline !== undefined) return inline;
      i += 1;
      return argv[i] ?? "";
    };
    if (flag === "--fixture") {
      fixture = true;
      continue;
    }
    if (flag === "--id") {
      id = next().trim();
      continue;
    }
    if (flag === "--out") {
      out = next().trim() || null;
      continue;
    }
    if (flag === "--base") {
      base = next().trim() || base;
      continue;
    }
    if (flag === "--authorization") {
      authorization = next().trim();
      continue;
    }
    if (flag === "--theme") {
      theme = next().trim() || null;
      continue;
    }
    if (flag === "--palette") {
      palette = next().trim() || null;
      continue;
    }
    if (flag === "--view") {
      view = next().trim() || null;
      continue;
    }
    return { ok: false, message: `Unknown argument ${token}` };
  }

  if (fixture && id) return { ok: false, message: "Pass --fixture or --id, not both" };
  if (!fixture && !id) return { ok: false, message: "Pass --id <conversationId> or --fixture" };
  if (!fixture) {
    const key = env.DIGICHAT_API_KEY?.trim();
    if (!authorization && key) authorization = `Bearer ${key}`;
    return {
      ok: true,
      plan: {
        mode: "conversation",
        id,
        out,
        baseUrl: base.replace(/\/$/, ""),
        authorization: authorization || null,
        theme,
        palette,
        view,
      },
    };
  }
  return { ok: true, plan: { mode: "fixture", out } };
}

export function conversationReplayUrl(plan: Extract<ReplayCliPlan, { mode: "conversation" }>): string {
  const url = new URL(`/api/conversations/${encodeURIComponent(plan.id)}/replay`, `${plan.baseUrl}/`);
  if (plan.theme) url.searchParams.set("theme", plan.theme);
  if (plan.palette) url.searchParams.set("palette", plan.palette);
  if (plan.view) url.searchParams.set("view", plan.view);
  return url.toString();
}

function splitFlag(token: string): [string, string | undefined] {
  const eq = token.indexOf("=");
  if (!token.startsWith("--") || eq === -1) return [token, undefined];
  return [token.slice(0, eq), token.slice(eq + 1)];
}
