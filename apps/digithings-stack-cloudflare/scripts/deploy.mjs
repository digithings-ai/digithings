/**
 * Deploy the digithings-stack Worker carrying DIGICHAT_CONTAINER_REV, so the
 * FOLDED digichat Container id is derived from the deploying commit (DIG-3814).
 *
 * WHY THIS FILE EXISTS, AND WHY IT IS NOT #5537.
 * digithings-stack is the surface that actually serves digichat traffic: the
 * zone routes moved here from the standalone Worker, so the fold is live and the
 * standalone Worker is deployable only for rollback. A derivation that reached
 * only the standalone Worker would leave the live surface pinned — "a partial
 * fix looks like the hole is closed while leaving it open".
 *
 * SCOPE — READ THIS BEFORE ASSUMING MORE. This wrapper carries the rev for the
 * FOLDED digichat Container only. The stack's OWN container id
 * (`SHARED_STACK_CONTAINER_ID`, still a hand-pinned "shared-v18") is a separate
 * defect belonging to DIG-3229 / PR #5537, which is OPEN and not merged; its
 * `sharedStackContainerId()` does not exist in this base. Do not read this file
 * as having fixed that one, and do not widen it to carry `STACK_CONTAINER_REV`
 * before #5537 lands — that would make two wrappers claim one variable.
 *
 *     git rev-parse --verify HEAD
 *       -> --var DIGICHAT_CONTAINER_REV:<sha12>
 *         -> digichat-mount -> sharedDigichatContainerId(env.DIGICHAT_CONTAINER_REV)
 *         -> "shared-<sha12>"
 *
 * ONE IMPLEMENTATION, NOT A COPY. The rev resolution, the sha gate, the `--var`
 * builder and the verdict all come from the digichat wrapper by import. Two
 * copies of "read the sha, refuse if it is not one" is exactly the drift this
 * ticket exists to remove, and the cross-package import is what makes a future
 * edit to the gate reach both deploy paths at once. `src/container-id-deploy.test.js`
 * in this package pins that the import is live and that the field this wrapper
 * verifies is the one the fold actually publishes.
 *
 * THE REUSE IS INTENTIONAL, NOT A LAYERING ACCIDENT: `resolveDeployRev`'s
 * default git cwd is the digichat package directory, which is in the same
 * repository and therefore the same commit. Only `main` is local, because it is
 * the one thing that must differ: it deploys THIS package's wrangler.toml and
 * reads THIS surface's meta route.
 *
 * Usage: `npm run deploy [-- <extra wrangler args>]`.
 */
import { spawnSync } from "node:child_process";
import { dirname, resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";

import {
  EXIT_DEPLOYED_UNVERIFIED,
  REV_VAR,
  buildVarArg,
  buildWranglerArgs,
  expectedContainerId,
  metaMatchesDeploy,
  resolveDeployRev,
  verdictFor,
} from "../../digichat-cloudflare/scripts/deploy.mjs";

/**
 * The stack's own meta route (same host as #5537 uses).
 *
 * It is a real zone route, so unlike the standalone Worker this deploy IS
 * verifiable over HTTP — the "deployed but not verifiable" arm below should
 * never be the steady state here.
 */
export const META_URL = "https://graph.digithings.ai/_stack/meta";

/**
 * Which key of `/_stack/meta` carries the folded digichat id.
 *
 * It is NOT `containerId`: that key is the stack's OWN container, owned by
 * DIG-3229. Verifying the wrong key would make this wrapper pass while the
 * folded digichat id stayed pinned — the exact failure it was added to prevent.
 */
export const META_FIELD = "digichatContainerId";

const APP_DIR = resolvePath(dirname(fileURLToPath(import.meta.url)), "..");

/** Re-exported so this package's tests can pin the shared contract in place. */
export { REV_VAR, buildVarArg, buildWranglerArgs, resolveDeployRev, metaMatchesDeploy };

/**
 * Read `/_stack/meta` and decide. A thin, stack-specific wrapper around the
 * shared verdict so the shared function stays free of stack-specific field
 * names.
 */
export function stackVerdict({ meta, expected, readError }) {
  return verdictFor({
    meta,
    expected,
    readError,
    metaUrl: META_URL,
    field: META_FIELD,
  });
}

async function readMeta() {
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
  return { meta, readError };
}

export async function main(extra) {
  const rev = resolveDeployRev();
  const expected = expectedContainerId(rev);
  process.stdout.write(
    `digithings-stack deploy: commit ${rev} -> folded digichat Container id ${expected}\n`,
  );

  const deployed = spawnSync("npm", buildWranglerArgs(rev, extra), {
    stdio: "inherit",
    cwd: APP_DIR,
  });
  if (typeof deployed.status === "number" && deployed.status !== 0) {
    process.exit(deployed.status);
  }

  const { meta, readError } = await readMeta();
  const verdict = stackVerdict({ meta, expected, readError });
  if (verdict.exitCode === 0) {
    process.stdout.write(`${verdict.message}\n`);
    return;
  }
  process.stderr.write(`${verdict.message}`);
  process.exit(verdict.exitCode === EXIT_DEPLOYED_UNVERIFIED ? verdict.exitCode : 1);
}

const invokedDirectly =
  process.argv[1] && fileURLToPath(import.meta.url) === resolvePath(process.argv[1]);
if (invokedDirectly) {
  main(process.argv.slice(2)).catch((err) => {
    process.stderr.write(`${err && err.message ? err.message : err}\n`);
    process.exit(1);
  });
}