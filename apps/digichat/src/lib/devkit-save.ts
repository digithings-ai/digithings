/**
 * digichat devkit — server-only save path (P1).
 *
 * Raw-save writes submitted draft text verbatim after restoring
 * `__DEVKIT_PRESERVED__` sentinels from disk, so formatting and comments
 * survive. Fail-closed throughout: gate at the route, realpath containment,
 * sentinel restore before parse, schema validation, scope check, `.bak`
 * backup, then write. Env-tenant entries are never writable.
 *
 * Server-only — never import from client components (node:fs, js-yaml).
 */

import {
  existsSync,
  readFileSync,
  realpathSync,
  statSync,
  writeFileSync,
  mkdtempSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve, sep, basename, dirname } from "node:path";
import { load as loadYaml } from "js-yaml";
// js-yaml v4 — default safe schema via load() with no schema override.
import {
  DEVKIT_SENTINEL,
  redactSecretLines,
  validateDevkitText,
  type DevkitValidation,
} from "./devkit-configs";

export type DevkitScope = ["deployment"] | ["hosts", string];

export type DevkitSaveRequest = {
  /**
   * Entry id: `file:<rel>`, `file:<rel>#hosts/<key>`, `env:<host>`
   * (refused), or `new:<slug>.yaml` (Step 5: create `config/<slug>.yaml`).
   */
  id: string;
  /** Full draft text (redacted view plus the operator's edits). */
  text: string;
};

export type DevkitSaveResult =
  | { ok: true; id: string; backup: string | null }
  | { ok: false; issues: string[] };

/**
 * Split an entry id into a repo-relative file path and an optional hosts
 * scope. Returns null for env ids and malformed ids (never writable).
 */
export function parseDevkitSaveId(id: string): { rel: string; scope: DevkitScope } | null {
  if (id.startsWith("env:")) return null;
  const fileMatch = /^file:([^#]+?)(?:#hosts\/([^/]+))?$/.exec(id);
  if (!fileMatch) return null;
  const [, rel, hostKey] = fileMatch;
  if (!rel || rel.length === 0) return null;
  return hostKey === undefined
    ? { rel, scope: ["deployment"] }
    : { rel, scope: ["hosts", hostKey] };
}

export type DevkitPathOptions = {
  /** Save-existing requires the file to exist; new-file creation relaxes this. */
  mustExist?: boolean;
};

/**
 * Config dir for the save path. Production code uses `<appRoot>/config`;
 * `DEVKIT_CONFIG_DIR` overrides it so route tests can point at a tmp dir
 * (absolute) instead of touching the real config tree. Dev-only surface —
 * never consulted in production builds (the route 404s there first).
 */
export function resolveDevkitConfigDir(): string {
  const override = process.env.DEVKIT_CONFIG_DIR;
  if (override && override.length > 0) return override;
  return resolve(process.cwd(), "config");
}

/**
 * Map a picker-style id rel (appRoot-relative, e.g. `config/examples/a.yaml`)
 * to a configDir-relative path. Strips one leading `<basename(configDir)>/`
 * segment — the picker's prefix for everything inside the config dir — and
 * passes anything else through untouched (bare names stay configDir-relative,
 * so tmp-dir callers are unaffected). Realpath containment downstream makes a
 * wrong guess fail closed, never misdirected.
 */
export function toConfigDirRel(configDir: string, rel: string): string {
  const prefix = `${basename(configDir)}/`;
  return rel.startsWith(prefix) ? rel.slice(prefix.length) : rel;
}

/**
 * Inverse of `toConfigDirRel` for responses: the picker-style rel the client
 * reselects on (`config/<inner>` in production).
 */
export function toPickerRel(configDir: string, innerRel: string): string {
  return `${basename(configDir)}/${innerRel}`;
}
/** New-file ids (`new:<slug>.yaml`): filename charset is the slug rule itself. */
export function parseDevkitNewFileId(id: string): { rel: string; slug: string } | null {
  const match = /^new:([a-z0-9-]+\.yaml)$/.exec(id);
  if (!match) return null;
  const rel = match[1];
  return { rel, slug: rel.slice(0, -".yaml".length) };
}

/**
 * Resolve a repo-relative YAML path inside `configDir`, fail-closed.
 * Rejects absolute paths, `..` escapes, non-YAML names, symlinks pointing
 * outside the config dir, and (with `mustExist`) missing/non-file targets.
 */
export function resolveDevkitFilePath(
  configDir: string,
  rel: string,
  options: DevkitPathOptions = {},
): string | null {
  if (rel.startsWith("/") || rel.includes("\\") || !rel.endsWith(".yaml")) return null;
  let root: string;
  try {
    root = realpathSync(configDir);
  } catch {
    return null;
  }
  const abs = resolve(root, rel);
  if (abs !== root && !abs.startsWith(root + sep)) return null;
  if (rel.split("/").includes("..")) return null;
  if (options.mustExist !== false) {
    let stat;
    try {
      stat = statSync(abs);
    } catch {
      return null;
    }
    if (!stat.isFile()) return null;
    // Contain symlinks too: the real target must stay inside the config dir.
    try {
      const real = realpathSync(abs);
      if (real !== root && !real.startsWith(root + sep)) return null;
    } catch {
      return null;
    }
  } else {
    // Create leg: the file itself can't be realpath'd (it doesn't exist
    // yet), so contain the parent dir instead — a symlinked parent
    // (e.g. `examples -> /elsewhere`) must not redirect the write.
    try {
      const realParent = realpathSync(dirname(abs));
      if (realParent !== root && !realParent.startsWith(root + sep)) return null;
    } catch {
      return null;
    }
  }
  return abs;
}

export type SentinelRestore =
  | { ok: true; text: string }
  | { ok: false; unresolved: string[] };

/**
 * Restore sentinels from disk at the text level, before YAML parsing.
 *
 * Every submitted line holding `__DEVKIT_PRESERVED__` must be byte-identical
 * to a masked line of the disk file's own redacted view; it is then replaced
 * with that line's original disk content (block-scalar continuations restore
 * line-for-line, so multi-line secrets round-trip exactly). A sentinel on a
 * line the operator added or modified has no disk counterpart and refuses —
 * retype the secret value instead. Multiset matching: submitting more copies
 * of a masked line than disk holds also refuses.
 */
export function restoreDevkitSentinels(
  submittedText: string,
  diskText: string,
): SentinelRestore {
  const diskLines = diskText.split("\n");
  const redactedDisk = redactSecretLines(diskText).split("\n");
  // Masked lines only: redacted form differs from disk form.
  const remaining = new Map<string, string[]>();
  for (let i = 0; i < redactedDisk.length; i++) {
    if (redactedDisk[i] !== diskLines[i]) {
      const bucket = remaining.get(redactedDisk[i]);
      if (bucket) bucket.push(diskLines[i]);
      else remaining.set(redactedDisk[i], [diskLines[i]]);
    }
  }
  const out: string[] = [];
  const unresolved: string[] = [];
  submittedText.split("\n").forEach((line, index) => {
    if (!line.includes(DEVKIT_SENTINEL)) {
      out.push(line);
      return;
    }
    const bucket = remaining.get(line);
    const diskLine = bucket?.shift();
    if (diskLine === undefined) {
      unresolved.push(`line ${index + 1}: redacted value has no on-disk counterpart`);
      out.push(line);
      return;
    }
    out.push(diskLine);
  });
  if (unresolved.length > 0) return { ok: false, unresolved };
  return { ok: true, text: out.join("\n") };
}

/** Scope guard: the edited file must still carry the entry being saved. */
function checkDevkitScope(
  restoredText: string,
  scope: DevkitScope,
): DevkitValidation {
  let parsed: unknown;
  try {
    parsed = loadYaml(restoredText);
  } catch (e) {
    return { ok: false, issues: [`(yaml): invalid YAML: ${(e as Error).message}`] };
  }
  const root =
    typeof parsed === "object" && parsed !== null
      ? (parsed as { deployment?: unknown; hosts?: Record<string, unknown> })
      : null;
  if (scope[0] === "deployment") {
    if (root && typeof root.deployment === "object" && root.deployment !== null) {
      return { ok: true, issues: [] };
    }
    return { ok: false, issues: ["(scope): top-level deployment missing after edit"] };
  }
  const hosts = root?.hosts;
  if (
    hosts &&
    typeof hosts === "object" &&
    typeof (hosts as Record<string, unknown>)[scope[1]] === "object" &&
    (hosts as Record<string, unknown>)[scope[1]] !== null
  ) {
    return { ok: true, issues: [] };
  }
  return { ok: false, issues: [`(scope): hosts/${scope[1]} missing after edit`] };
}

/**
 * Full save pipeline for one entry: id → contained path → disk read →
 * sentinel restore → residual scan → schema validation → scope check →
 * `.bak` → write. Returns issues instead of throwing (fail-closed).
 */
export function saveDevkitEntry(
  configDir: string,
  req: DevkitSaveRequest,
): DevkitSaveResult {
  const created = parseDevkitNewFileId(req.id);
  if (created) return saveDevkitNewFile(configDir, created, req.text);
  const parsed = parseDevkitSaveId(req.id);
  if (!parsed) {
    return {
      ok: false,
      issues: [`(id): not a writable entry: ${req.id} (env tenants are read-only)`],
    };
  }
  // Picker ids are appRoot-relative (`config/...`); resolve configDir-relative.
  const innerRel = toConfigDirRel(configDir, parsed.rel);
  const abs = resolveDevkitFilePath(configDir, innerRel);
  if (!abs) {
    return { ok: false, issues: [`(path): refused: ${parsed.rel} is outside the config dir`] };
  }
  let diskText: string;
  try {
    diskText = readFileSync(abs, "utf8");
  } catch {
    return { ok: false, issues: [`(read): cannot read ${parsed.rel}`] };
  }
  const restored = restoreDevkitSentinels(req.text, diskText);
  if (!restored.ok) {
    return { ok: false, issues: restored.unresolved };
  }
  if (restored.text.includes(DEVKIT_SENTINEL)) {
    return { ok: false, issues: ["(secrets): unresolved placeholder remains after restore"] };
  }
  const validation = validateDevkitText(restored.text);
  if (!validation.ok) return { ok: false, issues: validation.issues };
  const scope = checkDevkitScope(restored.text, parsed.scope);
  if (!scope.ok) return { ok: false, issues: scope.issues };
  try {
    writeFileSync(`${abs}.bak`, diskText);
    writeFileSync(abs, restored.text);
  } catch (e) {
    return { ok: false, issues: [`(write): ${(e as Error).message}`] };
  }
  return { ok: true, id: req.id, backup: `${parsed.rel}.bak` };
}

/**
 * Step 5 — new-file creation: `new:<slug>.yaml` writes `config/<slug>.yaml`.
 * No disk counterpart exists, so sentinels have nothing to restore from and
 * refuse (retype the value); no `.bak` either (nothing to back up — hence
 * `backup: null`). The filename slug must equal the validated
 * `deployment.slug`, so a stale client can't misfile the entry.
 */
function saveDevkitNewFile(
  configDir: string,
  created: { rel: string; slug: string },
  text: string,
): DevkitSaveResult {
  const abs = resolveDevkitFilePath(configDir, created.rel, { mustExist: false });
  if (!abs) {
    return {
      ok: false,
      issues: [`(path): refused: ${created.rel} is outside the config dir`],
    };
  }
  if (existsSync(abs)) {
    return {
      ok: false,
      issues: [`(exists): ${created.rel} already exists — pick another slug`],
    };
  }
  if (text.includes(DEVKIT_SENTINEL)) {
    return {
      ok: false,
      issues: ["(secrets): new files cannot carry redacted placeholders — type the value"],
    };
  }
  const validation = validateDevkitText(text);
  if (!validation.ok) return { ok: false, issues: validation.issues };
  let parsed: unknown;
  try {
    parsed = loadYaml(text);
  } catch (e) {
    return { ok: false, issues: [`(yaml): invalid YAML: ${(e as Error).message}`] };
  }
  const deployment =
    typeof parsed === "object" && parsed !== null
      ? (parsed as { deployment?: { slug?: unknown } }).deployment
      : undefined;
  if (deployment?.slug !== created.slug) {
    return {
      ok: false,
      issues: [
        `(slug): filename slug "${created.slug}" does not match deployment slug ${JSON.stringify(deployment?.slug ?? null)}`,
      ],
    };
  }
  const scope = checkDevkitScope(text, ["deployment"]);
  if (!scope.ok) return { ok: false, issues: scope.issues };
  try {
    writeFileSync(abs, text);
  } catch (e) {
    return { ok: false, issues: [`(write): ${(e as Error).message}`] };
  }
  // Picker-style id so the client can reselect the created entry verbatim.
  return { ok: true, id: `file:${toPickerRel(configDir, created.rel)}`, backup: null };
}

/** Test helper: fresh empty dir for save-path tests (no real file writes). */
export function makeDevkitTempDir(prefix: string): string {
  return mkdtempSync(`${tmpdir()}/${prefix}`);
}
