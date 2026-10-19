/**
 * Deploy the digithings-stack Worker with BOTH Container ids derived from the
 * deploying commit:
 *
 *     git rev-parse --verify HEAD
 *       -> --var STACK_CONTAINER_REV:<sha12>
 *         -> ports.ts: sharedStackContainerId(env.STACK_CONTAINER_REV)
 *         -> the stack's OWN Durable Object id (DIG-3229, landed by #5537)
 *       -> --var DIGICHAT_CONTAINER_REV:<sha12>
 *         -> digichat-mount -> digichat.ts: sharedDigichatContainerId(...)
 *         -> the FOLDED DIGICHAT Container id (DIG-3814, this PR)
 *       both -> "shared-<sha12>"
 *
 * WHY BOTH IN ONE DEPLOY. digithings-stack carries the zone routes and folds
 * the digichat Container, so one worker deploy has to ship both derivations.
 * A wrapper that carried only one rev would leave the other container id
 * hand-pinned — a partial fix looks like the hole is closed while leaving the
 * other half open.
 *
 * ONE IMPLEMENTATION, NOT A COPY. The rev resolution, the sha gate and the
 * expected-id builder all come from the digichat wrapper by import. Two copies
 * of "read the sha, refuse if it is not one" is exactly the drift this ticket
 * exists to remove, and the cross-package import is what makes a future edit
 * to the gate reach both deploy paths at once. The reuse is intentional, not a
 * layering accident: `resolveDeployRev`'s default git cwd is the digichat
 * package directory, which is in the same repository and therefore the same
 * commit. Only `main` stays stack-specific, because it deploys THIS package's
 * wrangler.toml and verifies THIS surface's meta route.
 *
 * Fail-closed and verify-afterwards carry over from DIG-3229 unchanged:
 *
 *  1. FAIL CLOSED. If the commit cannot be resolved, this script refuses to
 *     deploy. Deploying without a rev would silently pin the legacy id and
 *     reproduce exactly the defect it exists to remove, so the refusal is the
 *     correct failure: loud, at the desk, before anything is uploaded.
 *  2. VERIFY AFTERWARDS. After wrangler returns, `/_stack/meta` is read back
 *     from the live Worker and must report BOTH ids this commit implies. That
 *     catches a deploy that landed somewhere else and — the case that matters —
 *     a bypassing deploy that produced the legacy fallback.
 *
 * WHY A WORKER VAR AND NOT A BUILD-TIME DEFINE. The natural instrument is
 * `wrangler deploy --define KEY=VALUE`, measured broken in the pinned wrangler
 * 4.133.0: it rejects EVERY form, including the trivial `--define=FOO=bar`,
 * because wrangler passes the raw `KEY=VALUE` string to esbuild as an object
 * key and esbuild's `pushCommonFlags` throws `Invalid define: FOO=bar`. There
 * is no working substitution hook here, so the revs travel as Worker vars.
 * `--var` was measured to MERGE with the `[vars]` in wrangler.toml rather than
 * replace them (a dry run with `--var STACK_CONTAINER_REV:<sha>` still listed
 * SUPABASE_URL, DIGIVAULT_ROOT and MARKET_DATA_URL), which is why it is safe
 * here; the vars are deliberately absent from `[vars]` so they never become
 * hand-maintained keys that the config-contract and parity gates would pin.
 *
 * There is no CI deploy lane for this Worker (deleted 2026-10-01 by f54af7052,
 * #4919 Human Gate; see README "Deploy"), so this script plus `npm run deploy`
 * IS the deploy path. Keep it that way: the container ids are a function of
 * the commit only for as long as every deploy goes through it.
 *
 * Usage: `npm run deploy [-- <extra wrangler args>]`, e.g.
 *   npm run deploy -- --containers-rollout=none
 *
 * The `CLOUDFLARE_API_TOKEN` trap in wrangler.toml still applies to whatever
 * environment this is launched from: unset it for wrangler's own process (see
 * the README) — it is a Vectorize/D1 token and makes every deploy fail with
 * code 10000.
 */
import { spawnSync } from "node:child_process";
import { dirname, resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildVarArg as buildDigichatVarArg,
  expectedContainerId,
  metaMatchesDeploy as metaFieldMatches,
  resolveDeployRev,
  SHA_RE,
  REV_LEN,
} from "../../digichat-cloudflare/scripts/deploy.mjs";

/** Worker var carrying the stack's own rev (DIG-3229). Must match ports.ts / Env. */
export const REV_VAR = "STACK_CONTAINER_REV";

/** Worker var carrying the folded digichat rev (DIG-3814). Shared with the digichat wrapper. */
export const DIGICHAT_REV_VAR = "DIGICHAT_CONTAINER_REV";

export { expectedContainerId, resolveDeployRev, SHA_RE, REV_LEN };

/** Live, auth-exempt Worker route that reports the running Container id. */
export const META_URL = "https://graph.digithings.ai/_stack/meta";

/**
 * Which key of `/_stack/meta` carries the folded digichat id.
 *
 * It is NOT `containerId`: that key is the stack's OWN container, owned by
 * DIG-3229 / #5537. Verifying the wrong key would make this wrapper pass while
 * the folded digichat id stayed pinned — the exact failure this wrapper was
 * added to prevent.
 */
export const META_FIELD = "digichatContainerId";

const APP_DIR = resolvePath(dirname(fileURLToPath(import.meta.url)), "..");

/**
 * The wrangler flag that makes ports.ts derive the stack id from `rev`.
 *
 * `--var` takes KEY:VALUE (a colon, not an equals) and the value is a plain
 * string — no quoting. The sha shape is still checked here rather than trusted:
 * this string reaches the deployed Worker as a Durable Object name component,
 * and the one rev that must never get through is one that is not a sha.
 */
export function buildVarArg(rev) {
  if (typeof rev !== "string" || !SHA_RE.test(rev)) {
    throw new Error(
      `digithings-stack deploy REFUSED: refusing to build a --var from ${JSON.stringify(rev)}; ` +
        "expected a lowercase git sha.",
    );
  }
  return `--var=${REV_VAR}:${rev}`;
}

/**
 * The argv for `npm exec -- wrangler deploy`, always carrying exactly one rev
 * value feeding BOTH container ids, then the operator's extras. There is
 * deliberately no argv here that omits either var, which is the property the
 * whole ticket rests on: one deploy, both ids derived from one commit.
 */
export function buildWranglerArgs(rev, extra = []) {
  return ["exec", "--", "wrangler", "deploy", buildVarArg(rev), buildDigichatVarArg(rev), ...extra];
}

/** Does `/_stack/meta` .containerId (the stack's own) match this commit's id? */
export function metaMatchesDeploy(meta, expected) {
  return metaFieldMatches(meta, expected, "containerId");
}

/** Does `/_stack/meta` .digichatContainerId (the fold) match this commit's id? */
export function metaMatchesDigichat(meta, expected) {
  return metaFieldMatches(meta, expected, META_FIELD);
}

async function main(extra) {
  const rev = resolveDeployRev();
  const expected = expectedContainerId(rev);
  process.stdout.write(
    `digithings-stack deploy: commit ${rev} -> stack Container id ${expected}, ` +
      `folded digichat Container id ${expected}\n`,
  );

  const deployed = spawnSync("npm", buildWranglerArgs(rev, extra), {
    stdio: "inherit",
    cwd: APP_DIR,
  });
  if (typeof deployed.status === "number" && deployed.status !== 0) {
    process.exit(deployed.status);
  }

  let meta = null;
  let readError = null;
  try {
    const response = await fetch(META_URL, { headers: { accept: "application/json" } });
    if (response.ok) {
      meta = await response.json();
    } else {
      readError = `HTTP ${response.status}`;
    }
  } catch (err) {
    readError = String(err && err.message ? err.message : err);
  }

  const stackMatch = metaMatchesDeploy(meta, expected);
  const digichatMatch = metaMatchesDigichat(meta, expected);
  if (!stackMatch || !digichatMatch) {
    const missing = [];
    if (!stackMatch) missing.push("containerId (the stack's own id)");
    if (!digichatMatch) missing.push(`${META_FIELD} (the folded digichat id)`);
    process.stderr.write(
      "\ndigithings-stack deploy: DEPLOYED BUT UNVERIFIED\n" +
        `  expected ${META_URL} to report ${missing.join(" and ")}` +
        ` ${expected} for every field, none of them a legacy id\n` +
        `  it reported ${JSON.stringify(meta)} (read: ${readError ?? "ok"})\n` +
        "  A legacy id here means the bundle reached production without the rev, " +
        "so the running Container may still be the previous instance. Redeploy " +
        "with `npm run deploy` from a checkout (not a bare `npx wrangler deploy`).\n",
    );
    process.exit(1);
  }

  process.stdout.write(
    `digithings-stack deploy: ${META_URL} reports containerId ${meta.containerId} ` +
      `(stackRev ${meta.stackRev}) and ${META_FIELD} ${meta[META_FIELD]} ` +
      `(digichatRev ${meta.digichatRev}) — a fresh instance is guaranteed on both surfaces\n`,
  );
}

const invokedDirectly =
  process.argv[1] && fileURLToPath(import.meta.url) === resolvePath(process.argv[1]);
if (invokedDirectly) {
  main(process.argv.slice(2)).catch((err) => {
    process.stderr.write(`${err && err.message ? err.message : err}\n`);
    process.exit(1);
  });
}
