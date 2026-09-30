/**
 * Devkit export generators (P2). Pure string transforms, client-safe:
 * no node imports, no fetches. Everything builds from the live draft text.
 *
 * Secrets in draft text are either redacted sentinels or operator-typed
 * values on `token:` / `consumeUrl:` lines (mirroring SECRET_LINE_KEYS in
 * lib/devkit-configs.ts). Export never emits those values: compose bundles
 * substitute `${VAR}` placeholders and list every var on a setup checklist.
 */

export interface ExportSecret {
  /** 0-based line index in the source text. */
  line: number;
  key: "token" | "consumeUrl";
  variable: string;
  /** Human context, e.g. `deployment token` or `mcp server 'zammad'`. */
  context: string;
}

export interface ComposeBundle {
  slug: string;
  /** Draft text with secret lines replaced by `${VAR}` placeholders. */
  configYaml: string;
  envFragment: string;
  upCommand: string;
  checklist: string[];
  secrets: ExportSecret[];
  /** True when the draft still holds redaction sentinels (unsaved secrets). */
  hasSentinel: boolean;
}

const SENTINEL = "__DEVKIT_PRESERVED__";

const SECRET_LINE_RE = /^(\s*)(["']?)(token|consumeUrl)\2(\s*:)(.*)$/;
const SERVER_ID_RE = /^(\s*)-\s*id:\s*(\S+)\s*$/;
const TOKEN_ENV_RE = /^(\s*)tokenEnv:\s*(\S+)\s*$/;
const BLOCK_SCALAR_RE = /[|>][+-]?\s*(#.*)?$/;

function indentOf(line: string): number {
  return /^(\s*)/.exec(line)?.[1].length ?? 0;
}

function isBlank(line: string): boolean {
  return line.trim() === "";
}

function derivedServerVar(id: string): string {
  const clean = id
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return `${clean || "MCP_SERVER"}_TOKEN`;
}

/**
 * Scan the draft for secret-bearing lines and resolve each to an env var:
 * deployment `token:` → DIGICHAT_EMBED_TOKEN (loader convention),
 * `consumeUrl:` → DIGICHAT_CONSUME_URL, mcp server `token:` → the server's
 * `tokenEnv` when present, else a derived `<ID>_TOKEN`.
 */
export function detectExportSecrets(text: string): ExportSecret[] {
  const lines = text.split("\n");
  const found: ExportSecret[] = [];
  let serversIndent: number | null = null;
  let server: { id: string; tokenEnv: string | null; dashIndent: number } | null = null;

  const endServerIfDedented = (indent: number) => {
    if (server && indent <= server.dashIndent) server = null;
  };

  lines.forEach((line, i) => {
    if (isBlank(line)) return;
    const indent = indentOf(line);
    const trimmed = line.trim();

    if (/^servers:\s*(#.*)?$/.test(trimmed)) {
      serversIndent = indent;
      server = null;
      return;
    }
    if (serversIndent !== null && indent <= serversIndent) {
      serversIndent = null;
      server = null;
    }

    if (serversIndent !== null) {
      const idMatch = SERVER_ID_RE.exec(line);
      if (idMatch && indent > serversIndent) {
        server = { id: idMatch[2], tokenEnv: null, dashIndent: indent };
        return;
      }
      endServerIfDedented(indent);
      const envMatch = TOKEN_ENV_RE.exec(line);
      if (envMatch && server && indent > server.dashIndent) {
        server.tokenEnv = envMatch[2].replace(/^["']|["']$/g, "");
        return;
      }
    } else {
      endServerIfDedented(indent);
    }

    const secret = SECRET_LINE_RE.exec(line);
    if (!secret) return;
    const key = secret[3] as "token" | "consumeUrl";
    if (server && indent > server.dashIndent) {
      found.push({
        line: i,
        key,
        variable: server.tokenEnv ?? derivedServerVar(server.id),
        context: `mcp server '${server.id}'`,
      });
    } else if (key === "token") {
      found.push({ line: i, key, variable: "DIGICHAT_EMBED_TOKEN", context: "deployment token" });
    } else {
      found.push({ line: i, key, variable: "DIGICHAT_CONSUME_URL", context: "quota consume URL" });
    }
  });
  return found;
}

/** Replace secret lines with `${VAR}` placeholders; drop block continuations. */
function substituteSecrets(text: string, secrets: ExportSecret[]): string {
  const lines = text.split("\n");
  const byLine = new Map(secrets.map((s) => [s.line, s]));
  const out: string[] = [];
  let skipIndent: number | null = null;
  lines.forEach((line, i) => {
    if (skipIndent !== null) {
      if (isBlank(line) || indentOf(line) > skipIndent) return;
      skipIndent = null;
    }
    const hit = byLine.get(i);
    if (!hit) {
      out.push(line);
      return;
    }
    const m = SECRET_LINE_RE.exec(line);
    if (!m) {
      out.push(line);
      return;
    }
    out.push(`${m[1]}${m[2]}${hit.key}${m[2]}${m[4]} \${${hit.variable}}`);
    if (BLOCK_SCALAR_RE.test(m[5])) skipIndent = indentOf(line);
  });
  return out.join("\n");
}

const UP_COMMAND = "docker compose --profile digichat up --build";

/**
 * Build the local-launch bundle: placeholder-substituted config YAML, a
 * ready-to-fill `.env` fragment, the compose up command, and a checklist.
 * Grounded in the root compose `digichat` profile (config mounted at
 * /app/config:ro, selected via DIGICHAT_CONFIG_PATH, AUTH_SECRET fail-closed).
 */
export function buildComposeBundle(slug: string, text: string): ComposeBundle {
  const secrets = detectExportSecrets(text);
  const configYaml = substituteSecrets(text, secrets);
  const vars = [...new Set(secrets.map((s) => s.variable))];
  const envLines = [
    `# generated by digichat devkit export for '${slug}' — fill values, keep out of git`,
    "AUTH_SECRET= # required: openssl rand -base64 32 (compose fails fast without it)",
    "AUTH_URL=http://127.0.0.1:3005",
    "DIGICHAT_PUBLISH_PORT=3005",
    `DIGICHAT_CONFIG_PATH=/app/config/${slug}.yaml`,
    ...vars.map((v) => `${v}=`),
  ];
  const checklist = [
    `Save the config above to apps/digichat/config/${slug}.yaml (or point DIGICHAT_CONFIG_PATH at it).`,
    "Fill every empty value in the .env fragment (never commit real secrets).",
    `From the repo root: ${UP_COMMAND}`,
    "Open http://127.0.0.1:3005 and smoke-test, then /api/health.",
  ];
  if (secrets.length > 0) {
    checklist.push(
      `Set in env: ${vars.join(", ")} (${secrets.length} secret line${secrets.length === 1 ? "" : "s"} replaced by placeholders).`,
    );
  }
  return {
    slug,
    configYaml,
    envFragment: envLines.join("\n"),
    upCommand: UP_COMMAND,
    checklist,
    secrets,
    hasSentinel: text.includes(SENTINEL),
  };
}

export interface EmbedBundle {
  snippet: string;
  envLines: string;
  notes: string[];
}

/**
 * Build the parent-site embed snippet. Host defaults to the hosts-scope key
 * when the entry is one; otherwise the operator fills `<parent-host>`.
 * Token passes as `&token=…` unless the host is first-party registered.
 */
export function buildEmbedBundle(slug: string, host: string | null): EmbedBundle {
  const parentHost = host ?? "<parent-host>";
  const snippet = [
    `<iframe`,
    `  src="<chat-origin>/embed?host=${parentHost}&token=<embed-token>"`,
    `  width="100%"`,
    `  height="640"`,
    `  allow="clipboard-write; microphone"`,
    `  title="chat"></iframe>`,
  ].join("\n");
  const envLines = [
    `# parent-site embedding for '${slug}'`,
    `DIGICHAT_EMBED_HOSTS=${parentHost}`,
    `# token/backend live here, never in a build-arg:`,
    `# DIGICHAT_EMBED_TENANTS={"${parentHost}":{"slug":"${slug}","backend":{...}}}`,
  ].join("\n");
  const notes = [
    "Replace <chat-origin> with the public digichat origin and <embed-token> with the tenant token (first-party registered hosts may skip it).",
    "digichat sets frame-ancestors at runtime from DIGICHAT_EMBED_HOSTS (or tenant host keys) — never `*`.",
    "Smoke: /api/health, then open /embed?host=<parent-host>&token=…",
  ];
  return { snippet, envLines, notes };
}
