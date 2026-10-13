/**
 * Deploy the digithings-stack Worker with the Container id DERIVED FROM THE
 * DEPLOYING COMMIT (DIG-3229).
 *
 * Why this wrapper exists. `DigiStackContainer`'s Durable Object id used to be a
 * hand-edited string ("shared-v18") that every image-changing deploy had to
 * remember to bump, because `sleepAfter` alone does not evict a Container under
 * steady traffic and a code-only redeploy therefore leaves the old Firecracker
 * instance serving its old image. A forgotten bump ships no real fix while CI
 * stays green — and it had already cost two incidents (shared-v16 → v17, a
 * committed PII snapshot re-ingested on every cold start, DIG-1506/DIG-1500;
 * shared-v17 → v18, the digikey JWT scope-escalation build of #5283/#5010 still
 * in service). So the id is now built from the deploying commit inside
 * `src/ports.ts`, and this script is what feeds the commit in:
 *
 *     git rev-parse --verify HEAD
 *       -> --var STACK_CONTAINER_REV:<sha12>
 *         -> ports.ts: sharedStackContainerId(env.STACK_CONTAINER_REV)
 *         -> "shared-<sha12>"
 *
 * Two properties are deliberate, and both are pinned by
 * `src/container-id-deploy.test.js`:
 *
 *  1. FAIL CLOSED. If the commit cannot be resolved, this script refuses to
 *     deploy. Deploying without a rev would silently pin the legacy id and
 *     reproduce exactly the defect it exists to remove, so the refusal is the
 *     correct failure: loud, at the desk, before anything is uploaded.
 *  2. VERIFY AFTERWARDS. After wrangler returns, `/_stack/meta` is read back
 *     from the live Worker and must report the id this commit implies. That
 *     catches a deploy that landed somewhere else and — the case that matters —
 *     a bypassing deploy that produced the legacy fallback.
 *
 * WHY A WORKER VAR AND NOT A BUILD-TIME DEFINE. The natural instrument is
 * `wrangler deploy --define KEY=VALUE`, measured broken in the pinned wrangler
 * 4.133.0: it rejects EVERY form, including the trivial `--define=FOO=bar`,
 * because wrangler passes the raw `KEY=VALUE` string to esbuild as an object
 * key and esbuild's `pushCommonFlags` throws `Invalid define: FOO=bar`. There
 * is no working substitution hook here, so the rev travels as a Worker var.
 * `--var` was measured to MERGE with the `[vars]` in wrangler.toml rather than
 * replace them (a dry run with `--var STACK_CONTAINER_REV:<sha>` still listed
 * SUPABASE_URL, DIGIVAULT_ROOT and MARKET_DATA_URL), which is why it is safe
 * here; the var is deliberately absent from `[vars]` so it never becomes a
 * hand-maintained key that the config-contract and parity gates would pin.
 *
 * There is no CI deploy lane for this Worker (deleted 2026-10-01 by f54af7052,
 * #4919 Human Gate; see README "Deploy"), so this script plus `npm run deploy`
 * IS the deploy path. Keep it that way: the container id is a function of the
 * commit only for as long as every deploy goes through it.
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

/** Worker var carrying the rev. Must match ports.ts / the Env interface. */
export const REV_VAR = "STACK_CONTAINER_REV";

/** A git sha, short or full, lowercase hex. Anything else is refused. */
export const SHA_RE = /^[0-9a-f]{7,40}$/;

/** Hex chars that go into the Container id. 12 is what git --short=12 gives. */
export const REV_LEN = 12;

/** Live, auth-exempt Worker route that reports the running Container id. */
export const META_URL = "https://graph.digithings.ai/_stack/meta";

const APP_DIR = resolvePath(dirname(fileURLToPath(import.meta.url)), "..");

function defaultRunGit(args) {
  return spawnSync("git", args, { encoding: "utf8", cwd: APP_DIR });
}

/**
 * The short commit sha this deploy ships, or a throw.
 *
 * `runGit` is injected so the tests can drive every failure arm without a
 * repository. Nothing is defaulted silently: a non-zero status, an empty
 * stdout, or a stdout that is not a sha all refuse the deploy.
 */
export function resolveDeployRev(runGit = defaultRunGit) {
  const result = runGit(["rev-parse", "--verify", "HEAD"]) ?? {};
  const status = typeof result.status === "number" ? result.status : 1;
  const stdout = String(result.stdout ?? "").trim();
  const stderr = String(result.stderr ?? "").trim();

  if (status !== 0 || !SHA_RE.test(stdout)) {
    throw new Error(
      "digithings-stack deploy REFUSED: cannot resolve the deploying commit " +
        "with `git rev-parse --verify HEAD`.\n" +
        "Deploying without it would ship the legacy pinned Container id and " +
        "leave the previous instance serving its old image, which is the " +
        "defect this script exists to remove (DIG-3229). Run the deploy from " +
        "a checkout with a git history.\n" +
        `git status: ${status}; git stdout: ${JSON.stringify(stdout)}; ` +
        `git stderr: ${stderr || "<none>"}`,
    );
  }
  return stdout.slice(0, REV_LEN);
}

/**
 * The wrangler flag that makes ports.ts derive the id from `rev`.
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

/** The Container id this rev must produce. Mirrors ports.ts; a test pins the two together. */
export function expectedContainerId(rev) {
  return `shared-${rev}`;
}

/**
 * The argv for `npm exec -- wrangler deploy`, always carrying exactly one rev
 * var. There is deliberately no argv here that omits it, which is the property
 * the whole ticket rests on.
 */
export function buildWranglerArgs(rev, extra = []) {
  return ["exec", "--", "wrangler", "deploy", buildVarArg(rev), ...extra];
}

/** Does /_stack/meta prove the deploy this script just made is the one running? */
export function metaMatchesDeploy(meta, expected) {
  return Boolean(meta) && meta.containerId === expected;
}

async function main(extra) {
  const rev = resolveDeployRev();
  const expected = expectedContainerId(rev);
  process.stdout.write(
    `digithings-stack deploy: commit ${rev} -> Container id ${expected}\n`,
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

  if (!metaMatchesDeploy(meta, expected)) {
    process.stderr.write(
      "\ndigithings-stack deploy: DEPLOYED BUT UNVERIFIED\n" +
        `  expected ${META_URL} to report containerId ${expected}\n` +
        `  it reported ${JSON.stringify(meta && meta.containerId)} (stackRev ` +
        `${JSON.stringify(meta && meta.stackRev)}; read: ${readError ?? "ok"})\n` +
        "  A legacy id here means the bundle reached production without the rev, " +
        "so the running Container may still be the previous instance. Redeploy " +
        "with `npm run deploy` from a checkout (not a bare `npx wrangler deploy`).\n",
    );
    process.exit(1);
  }

  process.stdout.write(
    `digithings-stack deploy: ${META_URL} reports ${meta.containerId} ` +
      `(stackRev ${meta.stackRev}) — a fresh instance is guaranteed\n`,
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