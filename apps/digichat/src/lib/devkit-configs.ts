/**
 * digichat devkit — server-only config listing + secret redaction.
 *
 * Local dev workbench only: every consumer (API routes) must gate on
 * `isLocalBaselinePreview()` first. Secrets never leave this module —
 * file text is served with secret scalars replaced by `DEVKIT_SENTINEL`
 * and deployment objects are served with secret fields stripped.
 *
 * Server-only — never import from client components (node:fs, js-yaml).
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
// js-yaml v4 — default safe schema via load() with no schema override.
import type { z } from "zod";
import {
  DigichatConfigSchema,
  type DigichatConfig,
  type DigichatDeployment,
} from "./deploy-config/schema";
import { embedTenantToDeployment } from "./deploy-config/loader";
import { parseEmbedTenants } from "./embed-tenants";

/** Sentinel replacing secret scalars in served text (restored from disk on save). */
export const DEVKIT_SENTINEL = "__DEVKIT_PRESERVED__";

/** Scalar keys redacted line-wise from served YAML text. */
const SECRET_LINE_KEYS = new Set(["token", "consumeUrl"]);

export type DevkitEntry = {
  /** Stable id: `file:<relpath>`, `file:<relpath>#hosts/<key>`, or `env:<host>`. */
  id: string;
  kind: "file" | "env";
  /** Repo-relative posix path, or `DIGICHAT_EMBED_TENANTS` for env entries. */
  path: string;
  /** Deployment slug (file) or hostname (env). */
  label: string;
  readOnly: boolean;
  ok: boolean;
  issues: string[];
  /** Secret-redacted file text; null for env entries. */
  redactedText: string | null;
  /** Parsed deployment with secret fields stripped; null when invalid. */
  deployment: DigichatDeployment | null;
};

/**
 * Replace secret scalar lines (`token:`, `consumeUrl:`, quoted-key variants)
 * with the sentinel. Line-based so served text stays byte-identical to disk
 * except the redaction (raw save writes submitted text verbatim; save restores
 * sentinels from disk at schema-known paths). Block scalars (`token: |`)
 * mask the header plus every more-indented continuation line. Limitations:
 * a non-secret `token:` scalar nested somewhere unexpected (e.g. inside an
 * MCP `setup` map) is also masked — the save path restores only schema-known
 * secret paths, so such files must be edited knowing the masked line
 * round-trips through disk restore; multi-line flow scalars are not tracked.
 */
export function redactSecretLines(text: string): string {
  const lines = text.split("\n");
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const match = /^(\s*)(["']?)(token|consumeUrl)\2(\s*:)(.*)$/.exec(line);
    if (!match || !SECRET_LINE_KEYS.has(match[3])) {
      out.push(line);
      continue;
    }
    const [, indent, quote, key, colon, rest] = match;
    out.push(`${indent}${quote}${key}${quote}${colon} ${DEVKIT_SENTINEL}`);
    if (/^[|>]/.test(rest.trim())) {
      // Block scalar: mask continuation lines until indentation returns.
      const baseIndent = indent.length;
      let j = i + 1;
      while (j < lines.length) {
        const cont = lines[j];
        if (cont.trim() === "") {
          out.push(cont);
          j++;
          continue;
        }
        const contIndent = /^(\s*)/.exec(cont)?.[1].length ?? 0;
        if (contIndent <= baseIndent) break;
        out.push(`${/^(\s*)/.exec(cont)?.[1] ?? ""}${DEVKIT_SENTINEL}`);
        j++;
      }
      i = j - 1;
    }
  }
  return out.join("\n");
}

/** Strip operator secrets from a deployment before it leaves the server. */
export function stripDeploymentSecrets(dep: DigichatDeployment): DigichatDeployment {
  const next: DigichatDeployment = structuredClone(dep);
  delete next.token;
  if (next.gate) delete next.gate.consumeUrl;
  const servers = next.mcp?.servers;
  if (servers) {
    // `setup` is an arbitrary operator record forwarded verbatim to digigraph —
    // it must not reach the browser even though the client never renders it.
    for (const server of servers) {
      delete server.token;
      delete server.setup;
    }
  }
  return next;
}

export function formatDevkitIssues(error: z.ZodError): string[] {
  return error.issues.map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`);
}

export type DevkitValidation = { ok: boolean; issues: string[] };

/**
 * Single shared validator (schema is the one source of truth): validate an
 * already-parsed object. Used by the validate endpoint and, in P1, by save.
 */
export function validateDevkitObject(input: unknown): DevkitValidation {
  const result = DigichatConfigSchema.safeParse(input);
  if (result.success) return { ok: true, issues: [] };
  return { ok: false, issues: formatDevkitIssues(result.error) };
}

/** Validate raw YAML text: YAML syntax first, then the shared schema check. */
export function validateDevkitText(text: string): DevkitValidation {
  let parsed: unknown;
  try {
    parsed = loadYaml(text);
  } catch (e) {
    return { ok: false, issues: [`(yaml): invalid YAML: ${(e as Error).message}`] };
  }
  return validateDevkitObject(parsed);
}

function fileEntriesForConfig(
  relPath: string,
  raw: string,
): DevkitEntry[] {
  let parsed: unknown;
  try {
    parsed = loadYaml(raw);
  } catch (e) {
    const issues = [`(yaml): invalid YAML: ${(e as Error).message}`];
    return [
      {
        id: `file:${relPath}`,
        kind: "file",
        path: relPath,
        label: relPath,
        readOnly: false,
        ok: false,
        issues,
        redactedText: redactSecretLines(raw),
        deployment: null,
      },
    ];
  }
  const result = DigichatConfigSchema.safeParse(parsed);
  const redactedText = redactSecretLines(raw);
  if (!result.success) {
    return [
      {
        id: `file:${relPath}`,
        kind: "file",
        path: relPath,
        label: relPath,
        readOnly: false,
        ok: false,
        issues: formatDevkitIssues(result.error),
        redactedText,
        deployment: null,
      },
    ];
  }
  const config: DigichatConfig = result.data;
  const entries: DevkitEntry[] = [];
  if (config.deployment) {
    entries.push({
      id: `file:${relPath}`,
      kind: "file",
      path: relPath,
      label: config.deployment.slug,
      readOnly: false,
      ok: true,
      issues: [],
      redactedText,
      deployment: stripDeploymentSecrets(config.deployment),
    });
  }
  for (const [hostKey, dep] of Object.entries(config.hosts ?? {})) {
    entries.push({
      id: `file:${relPath}#hosts/${hostKey}`,
      kind: "file",
      path: relPath,
      label: dep.slug,
      readOnly: false,
      ok: true,
      issues: [],
      redactedText,
      deployment: stripDeploymentSecrets(dep),
    });
  }
  return entries;
}

function collectYamlFiles(configDir: string): string[] {
  const found: string[] = [];
  const walk = (dir: string, recursive: boolean): void => {
    let names: string[];
    try {
      names = readdirSync(dir);
    } catch {
      return;
    }
    for (const name of names.sort()) {
      if (name.startsWith(".")) continue;
      const abs = join(dir, name);
      let stat;
      try {
        stat = statSync(abs);
      } catch {
        continue;
      }
      if (stat.isDirectory()) {
        if (recursive) walk(abs, true);
        continue;
      }
      if (stat.isFile() && name.endsWith(".yaml")) found.push(abs);
    }
  };
  // Top level: config/*.yaml (non-recursive) + config/examples/** (recursive).
  walk(configDir, false);
  walk(join(configDir, "examples"), true);
  return found;
}

/**
 * List every devkit entry: local YAML files (parsed + redacted) and
 * `DIGICHAT_EMBED_TENANTS` hosts (read-only, secrets stripped).
 * `configDir` is the absolute `apps/digichat/config` dir; `appRoot` prefixes
 * repo-relative display paths.
 */
export function listDevkitEntries(
  configDir: string,
  env: NodeJS.ProcessEnv | Record<string, string | undefined> = process.env,
  appRoot: string = configDir,
): DevkitEntry[] {
  const entries: DevkitEntry[] = [];
  const root = resolve(appRoot);
  for (const abs of collectYamlFiles(configDir)) {
    const relPath = relative(root, abs).split("\\").join("/");
    let raw: string;
    try {
      raw = readFileSync(abs, "utf8");
    } catch {
      continue;
    }
    entries.push(...fileEntriesForConfig(relPath, raw));
  }

  const registry = parseEmbedTenants(env.DIGICHAT_EMBED_TENANTS);
  for (const [host, cfg] of registry) {
    entries.push({
      id: `env:${host}`,
      kind: "env",
      path: "DIGICHAT_EMBED_TENANTS",
      label: host,
      readOnly: true,
      ok: true,
      issues: [],
      redactedText: null,
      deployment: stripDeploymentSecrets(embedTenantToDeployment(cfg)),
    });
  }
  return entries;
}
