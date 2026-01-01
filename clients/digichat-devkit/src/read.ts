export const DASH = "—";

export type EntryKind = "file" | "env";

export type KitEntry = {
  id: string;
  kind: EntryKind;
  label: string;
  ok: boolean;
  issues: string[];
  /** Present only when the server sent redacted file text. Never a synthesized body. */
  redacted: boolean;
  deployment: Record<string, unknown> | null;
};

export type KitRead = {
  status: "ok" | "empty" | "down";
  detail: string;
  files: KitEntry[];
  envs: KitEntry[];
};

const down = (detail: string): KitRead => ({
  status: "down",
  detail,
  files: [],
  envs: [],
});

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function asEntry(raw: unknown): KitEntry | null {
  if (!isRecord(raw)) return null;
  if (typeof raw.id !== "string" || raw.id.length === 0) return null;
  if (typeof raw.label !== "string" || raw.label.length === 0) return null;
  if (raw.kind !== "file" && raw.kind !== "env") return null;
  const issues = Array.isArray(raw.issues)
    ? raw.issues.filter((item): item is string => typeof item === "string" && item.length > 0)
    : [];
  return {
    id: raw.id,
    kind: raw.kind,
    label: raw.label,
    ok: raw.ok === true,
    issues,
    redacted: typeof raw.redactedText === "string" && raw.redactedText.length > 0,
    deployment: isRecord(raw.deployment) ? raw.deployment : null,
  };
}

/** Map a configs response. Anything that is not the wire shape is a down read. */
export function interpretResponse(body: unknown): KitRead {
  if (!isRecord(body) || !Array.isArray(body.entries)) return down("configs unreadable");
  const entries = body.entries.map(asEntry).filter((entry): entry is KitEntry => entry !== null);
  if (entries.length !== body.entries.length) return down("configs unreadable");
  const files = entries.filter((entry) => entry.kind === "file");
  const envs = entries.filter((entry) => entry.kind === "env");
  if (entries.length === 0) {
    return { status: "empty", detail: "no deployments", files, envs };
  }
  return {
    status: "ok",
    detail: `${files.length} local files · ${envs.length} environment tenants`,
    files,
    envs,
  };
}

export function interpretHttp(status: number, body: unknown): KitRead {
  if (status !== 200) return down(`configs ${status}`);
  return interpretResponse(body);
}

export async function loadKit(baseUrl: string, signal?: AbortSignal): Promise<KitRead> {
  const root = baseUrl.replace(/\/+$/, "");
  try {
    const res = await fetch(`${root}/api/devkit/configs`, {
      signal,
      headers: { accept: "application/json" },
    });
    const text = await res.text();
    let body: unknown = null;
    if (text.length > 0) {
      try {
        body = JSON.parse(text) as unknown;
      } catch {
        body = null;
      }
    }
    return interpretHttp(res.status, body);
  } catch {
    return down("configs unreachable");
  }
}

/** First real deployment. Invalid rows stay listed and do not invent a config. */
export function selectedEntry(read: KitRead): KitEntry | null {
  const all = [...read.files, ...read.envs];
  return all.find((entry) => entry.ok && entry.deployment) ?? all.find((entry) => entry.deployment) ?? null;
}
