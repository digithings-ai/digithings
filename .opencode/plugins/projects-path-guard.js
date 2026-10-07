/**
 * Agent-runtime path guard — default-deny reads under `projects/*`.
 *
 * DIG-1302. Compensating control approved by the CTO on DIG-785: `projects/`
 * holds client data for every engagement, every agent runs as one unix user,
 * and the only barrier was a sentence in `AGENTS.md`. This plugin is the
 * barrier.
 *
 * Rule (Security's specification, DIG-1302):
 *   Default-deny under `projects/`. Allow exactly:
 *     1. `projects/README.md`          — tracked in git, not client data.
 *     2. `projects/<engagement-dir>/**` — the one engagement bound to this run.
 *   `<engagement-dir>` comes from an explicit engagement -> directory mapping
 *   (config/engagement-paths.json). It is never derived from the engagement
 *   name. An unbound engagement, a missing mapping entry, or an unevaluable
 *   path all resolve to DENY. Nothing falls through to allow.
 *
 * How a run is bound: the environment variable `DIGI_ENGAGEMENT` names the one
 * engagement for this run. Exactly one value, so a run cannot hold two
 * engagements' paths at once. Unset means no binding, which means no
 * allowlist beyond README.md.
 *
 * Kill switch: `DIGI_PROJECTS_PATH_GUARD=off` disables enforcement and the
 * plugin returns no hooks. Default is enforcing — a control that defaults off
 * is the residual risk restated. Every disablement is logged.
 *
 * Limits this code depends on (read before changing the shape):
 *   - Per tool call the guard does at most a handful of synchronous
 *     `fs.realpathSync` calls (one per path candidate, walking up to the
 *     deepest existing ancestor). It does no directory scans, no globbing and
 *     no network. Budget: single-digit `realpath` calls per tool call, so it
 *     stays inside opencode's per-call latency budget even on a cold FS cache.
 *   - One JSONL line per denial, appended synchronously. A denial storm writes
 *     linearly, never buffered in memory; there is no queue to grow.
 *   - The guard decides on paths only. It never reads, hashes or logs file
 *     contents — only the path that was refused.
 *   - Known limit: a shell command with no path argument at all, run from the
 *     repository root, can still enumerate directory *names* under `projects/`.
 *     Any token that resolves under `projects/` — including a bare `projects`
 *     and any glob like `projects/*` — is refused, so this is names, not
 *     content.
 */

import * as fs from "node:fs"
import * as path from "node:path"

/** Event name written to the audit trail. Mirrors digibase.audit event names. */
export const DENIAL_EVENT_TYPE = "projects_path_denied"

/** Kill-switch env var. */
export const FLAG_ENV = "DIGI_PROJECTS_PATH_GUARD"

/** Engagement binding for the current run. */
export const ENGAGEMENT_ENV = "DIGI_ENGAGEMENT"

/** Optional override for the engagement -> directory mapping file. */
export const MAPPING_ENV = "DIGI_ENGAGEMENT_MAP"

/** Optional JSONL audit sink. Absent means "no file", never "no evidence". */
export const AUDIT_LOG_ENV = "DIGI_PATH_GUARD_AUDIT_LOG"

const DEFAULT_MAPPING_RELPATH = "config/engagement-paths.json"

/** The one file under `projects/` that is never client data. */
export const ALWAYS_ALLOWED = "README.md"

/** A single directory segment. Anything else in the mapping is refused. */
const DIR_SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]*$/

/** True when the flag is not explicitly switched off. Fail-closed default. */
export function guardEnabled(env) {
  const raw = String(env[FLAG_ENV] ?? "").trim().toLowerCase()
  if (raw === "" || raw === "on" || raw === "true" || raw === "1" || raw === "enabled") return true
  if (raw === "off" || raw === "false" || raw === "0" || raw === "disabled") return false
  return true
}

/**
 * Resolve `absPath` through symlinks as far as the filesystem allows.
 *
 * The target of a read, grep or glob frequently does not exist yet, so we
 * realpath the deepest existing ancestor and re-attach the missing tail. That
 * is what defeats `projects/A/link` where `link -> ../B`: the link itself
 * exists, so it resolves, and the tail lands on the other engagement.
 *
 * Returns null when even the root cannot be resolved — the caller denies.
 */
export function realpathPrefix(absPath) {
  const tail = []
  let current = absPath
  for (;;) {
    try {
      const real = fs.realpathSync(current)
      return tail.length === 0 ? real : path.join(real, ...tail.reverse())
    } catch {
      const parent = path.dirname(current)
      if (parent === current) return null
      tail.push(path.basename(current))
      current = parent
    }
  }
}

/**
 * Read the engagement -> directory mapping.
 *
 * The mapping is data. An unreadable file, a malformed file, a shape we do not
 * recognise, or an engagement with no entry all return `null` for the
 * engagement directory, which the caller treats as "no allowlist".
 */
export function loadEngagementDir(mappingPath, engagement) {
  if (!engagement) return { dir: null, error: "no_engagement_bound" }
  let parsed
  try {
    parsed = JSON.parse(fs.readFileSync(mappingPath, "utf8"))
  } catch (err) {
    return { dir: null, error: `mapping_unreadable:${err.code ?? "eunknown"}` }
  }
  const engagements = parsed?.engagements
  if (!engagements || typeof engagements !== "object") {
    return { dir: null, error: "mapping_shape_unknown" }
  }
  const entry = engagements[engagement]
  if (!entry) return { dir: null, error: "mapping_no_entry" }
  const dir = typeof entry === "string" ? entry : entry?.dir
  if (typeof dir !== "string" || !DIR_SEGMENT.test(dir) || dir === "." || dir === "..") {
    return { dir: null, error: "mapping_dir_invalid" }
  }
  return { dir, error: null }
}

/**
 * Is `absPath` (already normalised and symlink-resolved) readable by this run?
 *
 * Paths outside `projects/` are not this guard's business and are allowed.
 * Paths inside it are allowed only for README.md and the bound engagement.
 */
export function classify(absPath, projectsRoot, engagementDir) {
  if (!absPath) return { decision: "deny", reason: "path_unevaluable" }
  if (absPath !== projectsRoot && !absPath.startsWith(projectsRoot + path.sep)) {
    return { decision: "allow", reason: "outside_projects" }
  }
  const rel = path.relative(projectsRoot, absPath)
  if (rel === ALWAYS_ALLOWED) return { decision: "allow", reason: "projects_readme" }
  if (engagementDir && (rel === engagementDir || rel.startsWith(engagementDir + path.sep))) {
    return { decision: "allow", reason: "bound_engagement" }
  }
  return {
    decision: "deny",
    reason: engagementDir ? "outside_bound_engagement" : "no_engagement_bound",
  }
}

/** Quote-aware split of a shell command into candidate path words. */
export function splitCommandWords(command) {
  const words = []
  let current = ""
  let started = false
  let quote = null
  for (let i = 0; i < command.length; i++) {
    const ch = command[i]
    if (quote) {
      if (ch === "\\" && quote === '"' && i + 1 < command.length) {
        current += command[++i]
        started = true
        continue
      }
      if (ch === quote) {
        quote = null
        started = true
        continue
      }
      current += ch
      started = true
      continue
    }
    if (ch === "'" || ch === '"') {
      quote = ch
      started = true
      continue
    }
    if (/\s/.test(ch)) {
      if (started) words.push(current)
      current = ""
      started = false
      continue
    }
    current += ch
    started = true
  }
  if (started) words.push(current)
  return words
}

const SHELL_NOISE = new Set([
  "|", "||", "&&", ";", ";", "&", ">>", ">", "<", "<<<", "2>", "2>>", "2>&1",
  "(", ")", "{", "}", "`", "$", "!", "\\",
])

const HAS_GLOB = /[*?[]/

/** Longest leading path that is guaranteed to contain every glob expansion. */
function staticPrefixOf(word) {
  const segments = word.split("/")
  const kept = []
  for (const segment of segments) {
    if (HAS_GLOB.test(segment)) break
    kept.push(segment)
  }
  if (kept.length === segments.length) return word
  return kept.join("/")
}

/**
 * Every filesystem candidate in a tool call, as absolute paths.
 *
 * Returns `{ paths, implicitRoot }`. `implicitRoot` is set for grep and glob
 * with no `path` argument: those tools walk the working directory, so a cwd
 * that contains `projects/` is itself a read of all of it.
 */
export function extractCandidates(tool, args, cwd) {
  const paths = []
  let implicitRoot = null
  const push = (word) => {
    if (typeof word !== "string" || word === "") return
    if (SHELL_NOISE.has(word)) return
    if (word.startsWith("-")) return
    const value = word.includes("=") && /^[A-Za-z_][A-Za-z0-9_]*=/.test(word)
      ? word.slice(word.indexOf("=") + 1)
      : word
    if (value === "" || SHELL_NOISE.has(value)) return
    const prefix = HAS_GLOB.test(value) ? staticPrefixOf(value) : value
    if (prefix === "" || prefix === "." || prefix === "/") return
    paths.push(path.resolve(cwd, prefix))
  }

  switch (tool) {
    case "read":
    case "edit":
    case "write":
      if (typeof args?.filePath === "string") push(args.filePath)
      break
    case "grep":
    case "list":
    case "glob":
      if (typeof args?.path === "string" && args.path !== "") push(args.path)
      else implicitRoot = cwd
      break
    case "bash":
      for (const word of splitCommandWords(String(args?.command ?? ""))) push(word)
      break
    default:
      // Any other tool that carries a path we can see. Unknown tools are not
      // silently trusted: if one of them names projects/, it is evaluated.
      if (typeof args?.filePath === "string") push(args.filePath)
      if (typeof args?.path === "string") push(args.path)
      break
  }
  return { paths, implicitRoot }
}

/** Is `absPath` the bound engagement subtree? */
function isBound(absPath, projectsRoot, engagementDir) {
  if (!engagementDir) return false
  const rel = path.relative(projectsRoot, absPath)
  return rel === engagementDir || rel.startsWith(engagementDir + path.sep)
}

/**
 * Build the guard. Pure apart from the `log`/`append` sinks, so the tests can
 * drive it without a filesystem-backed opencode session.
 */
export function createGuard({ env = {}, cwd, repoRoot, mappingPath }) {
  const realRoot = realpathPrefix(repoRoot) ?? path.resolve(repoRoot)
  // Built from the resolved repo root rather than resolved from `projects/`
  // itself: if `projects/` is absent the guard must still refuse paths that
  // point into it.
  const projectsRoot = path.join(realRoot, "projects")
  const mapping = mappingPath || path.join(realRoot, DEFAULT_MAPPING_RELPATH)

  return {
    projectsRoot,
    mappingPath: mapping,
    /** Re-read on every call so a mapping edit lands without a restart. */
    config() {
      const engagement = String(env[ENGAGEMENT_ENV] ?? "").trim()
      const { dir, error } = loadEngagementDir(mapping, engagement)
      return { engagement, engagementDir: dir, mappingError: error }
    },
    /**
     * Decide one tool call. Returns
     * `{ decision: "allow" | "deny", reason, tool, candidates, denied }`.
     */
    evaluate(tool, args) {
      const { engagement, engagementDir, mappingError } = this.config()
      const { paths, implicitRoot } = extractCandidates(tool, args ?? {}, cwd)

      if (implicitRoot) {
        const resolvedCwd = realpathPrefix(path.resolve(implicitRoot))
        const insideProjects =
          resolvedCwd === projectsRoot ||
          (resolvedCwd !== null && resolvedCwd.startsWith(projectsRoot + path.sep))
        if (!resolvedCwd) {
          return this.deny(path.resolve(implicitRoot), "path_unevaluable", engagement, mappingError, tool)
        }
        // A tool with no path argument walks its cwd, so a cwd that *contains*
        // projects/ is a read of all of it. The repo root always does.
        if (!insideProjects) {
          return this.deny(resolvedCwd, "implicit_projects_scan", engagement, mappingError, tool)
        }
        // A cwd inside the bound engagement is fine: the scan stays in scope.
        if (!isBound(resolvedCwd, projectsRoot, engagementDir)) {
          return this.deny(resolvedCwd, "outside_bound_engagement", engagement, mappingError, tool)
        }
      }

      const denied = []
      let firstVerdict = null
      for (const candidate of paths) {
        const resolved = realpathPrefix(candidate)
        if (!resolved) {
          denied.push({ path: candidate, reason: "path_unevaluable" })
          continue
        }
        const verdict = classify(resolved, projectsRoot, engagementDir)
        firstVerdict ??= verdict
        if (verdict.decision === "deny") {
          denied.push({ path: resolved, raw: candidate, reason: verdict.reason })
        }
      }
      if (denied.length > 0) {
        return { decision: "deny", reason: denied[0].reason, tool, candidates: denied, denied: true, engagement, mappingError }
      }
      return {
        decision: "allow",
        reason: firstVerdict?.reason ?? "no_path_argument",
        tool,
        candidates: [],
        denied: false,
        engagement,
        mappingError,
      }
    },

    /** Deny helper so every refusal shares one shape and one audit path. */
    deny(candidate, reason, engagement, mappingError, tool) {
      return {
        decision: "deny",
        reason,
        tool: tool ?? "",
        candidates: [{ path: candidate, reason, implicit: true }],
        denied: true,
        engagement,
        mappingError,
      }
    },
  }
}

/** One JSONL audit line. Shape mirrors `digibase.audit.AuditEvent`. */
export function auditLine({ tool, reason, engagement, mappingError, denied, projectsRoot, agentId, now = () => new Date() }) {
  return JSON.stringify({
    ts: now().toISOString(),
    event_type: DENIAL_EVENT_TYPE,
    agent_id: agentId ?? "",
    payload: {
      decision: "deny",
      tool: tool ?? "",
      reason: reason ?? "",
      engagement: engagement ?? "",
      mapping_error: mappingError ?? null,
      projects_root: projectsRoot ?? "",
      denied_paths: denied.map((entry) => entry.path),
      implicit_scan: denied.some((entry) => entry.implicit === true),
    },
  })
}

/** Denial message handed back to the model. Names the fix, not just the refusal. */
export function denialMessage(verdict, { engagement, engagementDir }) {
  const paths = verdict.candidates.map((entry) => entry.path).join(", ")
  const binding = engagementDir
    ? `This run is bound to engagement "${engagement}" (projects/${engagementDir}/).`
    : `This run has no bound engagement, so nothing under projects/ is readable. Set ${ENGAGEMENT_ENV} to the engagement id for this run.`
  return [
    `Path guard denied this ${verdict.tool} call (${verdict.reason}).`,
    `Refused: ${paths}`,
    binding,
    `projects/README.md is always readable. ${FLAG_ENV}=off disables the guard, but that re-opens the finding this guard closes.`,
  ].join(" ")
}

export const ProjectsPathGuard = async (input) => {
  const env = process.env
  if (!guardEnabled(env)) {
    await logToClient(input, "warn", `projects-path-guard disabled by ${FLAG_ENV}=off — projects/* is unguarded`, {})
    return {}
  }

  const repoRoot = input?.worktree || input?.directory || process.cwd()
  const cwd = input?.directory || repoRoot
  const auditLogPath = env[AUDIT_LOG_ENV] || null
  const agentId = env.PAPERCLIP_AGENT_ID || ""

  const guard = createGuard({
    env,
    cwd,
    repoRoot,
    mappingPath: env[MAPPING_ENV] || null,
  })

  return {
    "tool.execute.before": async (hookInput, output) => {
      const verdict = guard.evaluate(hookInput.tool, output?.args ?? {})
      if (verdict.decision !== "deny") return

      const { engagement, engagementDir } = guard.config()
      const line = auditLine({
        tool: hookInput.tool,
        reason: verdict.reason,
        engagement,
        mappingError: verdict.mappingError,
        denied: verdict.candidates,
        projectsRoot: guard.projectsRoot,
        agentId,
      })
      let auditWritten = true
      try {
        if (auditLogPath) fs.appendFileSync(auditLogPath, line + "\n")
        await logToClient(input, "warn", line, { sessionID: hookInput.sessionID, callID: hookInput.callID })
      } catch (err) {
        // The refusal does not depend on the audit write succeeding. It is
        // reported in the message so a broken sink is visible, not silent.
        auditWritten = false
        await logToClient(input, "error", `projects-path-guard audit write failed: ${err}`, {})
      }

      const message = auditWritten
        ? denialMessage(verdict, { engagement, engagementDir })
        : `${denialMessage(verdict, { engagement, engagementDir })}\nWARNING: the denial audit event could not be written.`
      throw new Error(message)
    },
  }
}

async function logToClient(input, level, message, extra) {
  try {
    await input?.client?.app?.log({
      body: { service: "projects-path-guard", level, message, extra },
    })
  } catch {
    // Logging must never change a decision.
  }
}