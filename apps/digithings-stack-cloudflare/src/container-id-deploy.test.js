import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  buildVarArg as buildDigichatVarArg,
  metaMatchesDeploy as sharedMetaFieldMatches,
  resolveDeployRev as sharedResolveDeployRev,
  REV_VAR as DIGICHAT_WRAP_REV_VAR,
} from "../../digichat-cloudflare/scripts/deploy.mjs";
import { STACK_CONTAINER_REV_VAR, sharedStackContainerId } from "./ports";
import {
  DIGICHAT_REV_VAR,
  META_FIELD,
  META_URL,
  REV_LEN,
  REV_VAR,
  SHA_RE,
  buildVarArg,
  buildWranglerArgs,
  expectedContainerId,
  metaMatchesDeploy,
  metaMatchesDigichat,
  resolveDeployRev,
} from "../scripts/deploy.mjs";
import { sharedDigichatContainerId } from "./digichat";

/**
 * DIG-3229 + DIG-3814, merged: the stack deploy path carries BOTH revs now —
 * the stack's OWN Durable Object id (ports.ts) and the digichat Container id
 * derived from the same commit (re-exported through digichat.ts). A derivation
 * is only worth anything if every deploy actually carries its rev, because a
 * deploy without it silently falls back to the pinned legacy id. That is a
 * property of the DEPLOY PATH, not of the derivation, so it is pinned here: the
 * rev resolution (shared by import with the digichat wrapper), the wrangler
 * argv, the package script operators run, and the post-deploy read-back of BOTH
 * /_stack/meta fields.
 *
 * The property that matters most is not "the wrapper carries a rev" — it is
 * that the wrapper verifies BOTH meta fields, each under its own key.
 * `/_stack/meta` publishes two different container ids: `containerId` is the
 * stack's own and `digichatContainerId` is the digichat one this commit derives.
 * A wrapper pointed at the wrong key would either fail forever or, worse, pass
 * while the digichat id stayed pinned. Every digichat-id assertion below is
 * built around that distinction, and the discriminating arm is a meta payload
 * carrying ONLY the stack's own id: the digichat check must refuse it rather
 * than call it verified.
 *
 * Since the 2026-10-19 separation this Worker does not serve digichat paths and
 * mounts no digichat container; the `digichatContainerId` field is reported for
 * this one read-back, not because a route here answers to it.
 *
 * Deliberately plain `.js` (same reason as container-bind.test.js /
 * env-vars-pin.test.js): tsconfig.json scopes `types` to
 * @cloudflare/workers-types only, so node:fs / node:path / node:url have no
 * ambient declarations in a `.ts` file here. vitest runs it via the
 * `.test.{ts,js}` glob in vitest.config.ts.
 */
const here = dirname(fileURLToPath(import.meta.url));
const appDir = join(here, "..");

/** A git stand-in that records the argv it was handed, so the success arm proves itself. */
function fakeGit({ status = 0, stdout = "", stderr = "" } = {}) {
  const calls = [];
  const run = (args) => {
    calls.push(args);
    return { status, stdout, stderr };
  };
  run.calls = calls;
  return run;
}

const FULL_SHA = "822af7515ab6d0e9f1c2b3a4d5e6f708192a3b4c";
const SHORT_REV = FULL_SHA.slice(0, REV_LEN);

describe("resolveDeployRev", () => {
  it("is the digichat wrapper's implementation, not a stack-local copy", () => {
    // Live-import proof (DIG-3814): if this were copied, editing the shared
    // gate would leave the stack wrapper behind and the hole would reopen on
    // the live surface. Identity against the shared module is the strongest
    // available statement.
    expect(resolveDeployRev).toBe(sharedResolveDeployRev);
  });

  it("resolves the short commit sha, asking git for the verified HEAD", () => {
    const git = fakeGit({ stdout: `${FULL_SHA}\n` });
    expect(resolveDeployRev(git)).toBe(SHORT_REV);
    // The argv is asserted so the success arm is not satisfied by a stand-in
    // that ignores its argument: this is the call whose failure refuses a deploy.
    expect(git.calls).toEqual([["rev-parse", "--verify", "HEAD"]]);
    expect(SHORT_REV).toHaveLength(12);
    expect(SHA_RE.test(SHORT_REV)).toBe(true);
  });

  it("REFUSES the deploy when git fails (no history, wrong cwd, not a repo)", () => {
    const git = fakeGit({ status: 128, stdout: "", stderr: "fatal: not a git repository" });
    expect(() => resolveDeployRev(git)).toThrow(/REFUSED/);
    expect(() => resolveDeployRev(git)).toThrow(/rev-parse --verify HEAD/);
  });

  it("REFUSES the deploy when git exits 0 but prints nothing", () => {
    // A detached/empty checkout can exit 0 with empty output; treating that as
    // a rev would deploy an id derived from the empty string.
    expect(() => resolveDeployRev(fakeGit({ stdout: "\n" }))).toThrow(/REFUSED/);
  });

  it("REFUSES a rev that is not a sha, so a ref name can never become the id", () => {
    for (const bad of ["v18", "HEAD", "origin/develop", "not-a-sha-at-all", "822AF7515AB", "deadbeefz"]) {
      expect(SHA_RE.test(bad)).toBe(false);
      expect(() => resolveDeployRev(fakeGit({ stdout: bad }))).toThrow(/REFUSED/);
    }
  });
});

describe("buildVarArg (the stack's own rev var)", () => {
  it("passes the rev as KEY:VALUE, unwrapped — a var, not a JSON literal", () => {
    expect(buildVarArg(SHORT_REV)).toBe(`--var=${REV_VAR}:${SHORT_REV}`);
    // `--var` takes a colon separator and a bare value; quoting it would put
    // literal quote characters into the Durable Object name.
    expect(buildVarArg(SHORT_REV)).not.toContain('"');
  });

  it("refuses to build a var from anything that is not a sha", () => {
    for (const bad of [undefined, null, "", "v18", "822af7515ab; rm -rf /", 42]) {
      expect(() => buildVarArg(bad)).toThrow(/REFUSED/);
    }
  });
});

describe("buildWranglerArgs", () => {
  it("always carries BOTH rev vars for ONE commit: there is no one-id argv", () => {
    const args = buildWranglerArgs(SHORT_REV);
    expect(args.slice(0, 4)).toEqual(["exec", "--", "wrangler", "deploy"]);
    expect(args.filter((a) => a.startsWith("--var="))).toEqual([
      buildVarArg(SHORT_REV),
      `--var=${DIGICHAT_REV_VAR}:${SHORT_REV}`,
    ]);
  });

  it("builds the digichat rev var through the shared wrapper's own builder", () => {
    // Same identity proof as resolveDeployRev, one level up: the digichat-side
    // --var string is built by the digichat module, not re-spelled here.
    expect(buildDigichatVarArg(SHORT_REV)).toBe(`--var=${DIGICHAT_REV_VAR}:${SHORT_REV}`);
    expect(DIGICHAT_REV_VAR).toBe(DIGICHAT_WRAP_REV_VAR);
  });

  it("passes operator arguments through without dropping either rev var", () => {
    const args = buildWranglerArgs(SHORT_REV, ["--containers-rollout=none"]);
    expect(args).toContain("--containers-rollout=none");
    expect(args.filter((a) => a.startsWith("--var="))).toHaveLength(2);
  });

  it("cannot be built at all without a valid rev", () => {
    // The property the ticket rests on: refusing to produce argv is what stops
    // a deploy from shipping without the rev.
    expect(() => buildWranglerArgs(undefined)).toThrow(/REFUSED/);
    expect(() => buildWranglerArgs("v18")).toThrow(/REFUSED/);
  });
});

describe("the deploy path carries both revs", () => {
  const pkg = JSON.parse(
    readFileSync(join(appDir, "package.json"), "utf-8"),
  );

  it("`npm run deploy` is the wrapper, not a bare wrangler deploy", () => {
    // README "Deploy" documents this as the whole deploy path (no CI lane,
    // #4919). If this ever points at `wrangler deploy` again, the rev is
    // optional again and the manual bump returns with it.
    expect(pkg.scripts.deploy).toContain("scripts/deploy.mjs");
    expect(pkg.scripts.deploy).not.toMatch(/wrangler deploy/);
  });

  it("the stack rev var name is one string across the script, ports.ts and Env", () => {
    // Three files, three spellings of the same key. A typo in any of them
    // yields a var nothing reads, i.e. a silent fall back to the legacy id.
    expect(REV_VAR).toBe(STACK_CONTAINER_REV_VAR);
    const index = readFileSync(join(appDir, "src", "index.ts"), "utf-8");
    expect(index).toContain(`${REV_VAR}?: string;`);
    expect(index).toContain(`workerEnv.${REV_VAR}`);
    expect(sharedStackContainerId("822af7515ab")).toBe("shared-822af7515ab");
  });

  it("the digichat rev var name is one string across script, Env and the fold", () => {
    const index = readFileSync(join(appDir, "src", "index.ts"), "utf-8");
    expect(index).toContain(`${DIGICHAT_REV_VAR}?: string;`);
    expect(index).toContain(`workerEnv.${DIGICHAT_REV_VAR}`);
    expect(sharedDigichatContainerId("822af7515ab")).toBe("shared-822af7515ab");
  });

  it("the rev vars are NOT hand-written into wrangler.toml [vars]", () => {
    // A committed value would be a manual step again — and would pull the keys
    // into the config-contract and self-host parity gates that pin every
    // [vars] entry. The deploy injects them; the config must not carry them.
    const toml = readFileSync(join(appDir, "wrangler.toml"), "utf-8");
    const assigned = [...toml.matchAll(/^\s*([A-Z_]+)\s*=\s/gm)].map((m) => m[1]);
    expect(assigned).not.toContain(REV_VAR);
    expect(assigned).not.toContain(DIGICHAT_REV_VAR);
    // Control: the census above really does see this file's assignments.
    expect(assigned).toContain("SUPABASE_URL");
  });

  it("does not use `wrangler deploy --define`, which is broken in wrangler 4.133.0", () => {
    // Measured, not assumed: `--define=FOO=bar` is rejected with
    // `Invalid define: FOO=bar` by the pinned wrangler, so a define-based
    // rewrite of this fix cannot work. Pinned so nobody "simplifies" the
    // wrapper back onto a dead instrument.
    const script = readFileSync(join(appDir, "scripts", "deploy.mjs"), "utf-8");
    const argv = buildWranglerArgs(SHORT_REV);
    expect(argv.filter((a) => a.startsWith("--define"))).toEqual([]);
    // The finding itself stays recorded where the next reader will meet it.
    expect(script).toContain("--define=FOO=bar");
  });

  it("ports.ts declares no hand-edited Container id except the named fallback", () => {
    // The regression this ticket closes. A declaration of the shape
    // `const X_CONTAINER_ID = "shared-vNN"` is the manual bump; only the
    // explicitly-named legacy fallback may carry one, and it is what a build
    // without a rev falls back to.
    const ports = readFileSync(join(appDir, "src", "ports.ts"), "utf-8");
    const declarations = [
      ...ports.matchAll(/(?:export )?const [A-Z_]*CONTAINER_ID = "shared-v\d+"/g),
    ].map((m) => m[0]);
    expect(declarations).toEqual([
      'export const LEGACY_SHARED_STACK_CONTAINER_ID = "shared-v18"',
    ]);
  });

  it("exactly ONE getContainer call addresses the shared stack", () => {
    // Not "three call sites each pass the rev" but one helper every route goes
    // through: a new shared-stack route then cannot forget the rev, because
    // there is no second place to write the id by hand.
    const index = readFileSync(join(appDir, "src", "index.ts"), "utf-8");
    const direct = index.match(/getContainer\(workerEnv\.STACK,/g);
    expect(direct).toHaveLength(1);
    const throughHelper = index.match(/stackContainer\(workerEnv\)/g);
    // 1 declaration is not a call: 3 route groups call it.
    expect(throughHelper).toHaveLength(3);
  });

  it("the ONE helper that builds the id reads the rev var and passes it on", () => {
    // Scoped to the helper body on purpose. A whole-file `toContain` of this
    // call survived a mutant that rewrote it to `sharedStackContainerId(undefined)`:
    // the /_stack/meta line carries the identical substring and satisfied the
    // check, so the suite stayed green while the deployment fell back to the
    // legacy id — the exact defect this ticket closes. Pin the body.
    const index = readFileSync(join(appDir, "src", "index.ts"), "utf-8");
    const helper = index.match(/function stackContainer\(workerEnv: Env\)[\s\S]*?\n\}/);
    if (!helper) {
      throw new Error("could not locate `function stackContainer(workerEnv: Env)` in index.ts");
    }
    // Non-empty and doing the work, so the pins below cannot pass on an
    // extracted stub.
    expect(helper[0]).toContain("getContainer(");
    expect(helper[0]).toContain(`sharedStackContainerId(workerEnv.${REV_VAR})`);
    // And it is the id that is derived, not merely computed and discarded.
    expect(helper[0]).toMatch(/getContainer\(\s*workerEnv\.STACK,\s*sharedStackContainerId\(/);
  });

  it("the stack reports the derived digichat id but fetches no digichat container", () => {
    // DIG-3814's stack half, after the 2026-10-19 separation: the
    // container is gone (the client surface lives on the digithings-digichat
    // Worker), and what remains here is the derived-id report in /_stack/meta
    // that the shared deploy wrapper verifies. No hand-pinned literal either.
    const index = readFileSync(join(appDir, "src", "index.ts"), "utf-8");
    expect(index).not.toContain("SHARED_DIGICHAT_CONTAINER_ID");
    expect(index).not.toContain("SHARED_STACK_CONTAINER_ID");
    expect(index).not.toContain("getContainer(workerEnv.DIGICHAT");
    expect(index).not.toContain("switchPort(request, DIGICHAT_PORT)");
    expect(index).toContain(
      "digichatContainerId: sharedDigichatContainerId(workerEnv.DIGICHAT_CONTAINER_REV)",
    );
  });

  it("every read of the rev var is consumed as a call argument", () => {
    // Independent of the helper pin: a read that is computed and thrown away is
    // the silent-fallback class, and a count cannot be faked by a rename.
    // String.raw on purpose: a doubly-escaped pattern silently matches nothing,
    // and a check that fails on the CLEAN tree cannot discriminate anything.
    const index = readFileSync(join(appDir, "src", "index.ts"), "utf-8");
    // `workerEnv`, capital E — a lowercase `env\.` matches nothing here and
    // that failure is silent. Pin the exact token.
    const reads = [...index.matchAll(new RegExp(String.raw`workerEnv\.${REV_VAR}\b`, "g"))].length;
    const consumed = [
      ...index.matchAll(
        new RegExp(String.raw`\(\s*workerEnv\.${REV_VAR}\s*\)`, "g"),
      ),
    ].length;
    expect(reads).toBeGreaterThan(0);
    expect(consumed).toBe(reads);
  });

  it("/_stack/meta reports BOTH ids and both revs, so a deploy can be verified", () => {
    const index = readFileSync(join(appDir, "src", "index.ts"), "utf-8");
    expect(index).toContain(
      "containerId: sharedStackContainerId(workerEnv.STACK_CONTAINER_REV)",
    );
    expect(index).toContain("stackRev: stackContainerRev(workerEnv.STACK_CONTAINER_REV)");
    expect(index).toContain(
      "digichatContainerId: sharedDigichatContainerId(workerEnv.DIGICHAT_CONTAINER_REV)",
    );
    expect(index).toContain("digichatRev: digichatContainerRev(workerEnv.DIGICHAT_CONTAINER_REV)");
  });
});

describe("the wrapper and ports.ts agree on the id", () => {
  it("expectedContainerId matches the derivation for the same rev", () => {
    // The two halves live in different files (a build-time script and a
    // bundled module); a drift here would make the post-deploy check report a
    // false alarm, so it is pinned rather than trusted.
    expect(expectedContainerId(SHORT_REV)).toBe(sharedStackContainerId(SHORT_REV));
  });
});

describe("metaMatchesDeploy (the stack's own field)", () => {
  it("accepts the id this commit implies", () => {
    expect(
      metaMatchesDeploy({ containerId: expectedContainerId(SHORT_REV) }, expectedContainerId(SHORT_REV)),
    ).toBe(true);
  });

  it("rejects the legacy fallback — the bypassing-deploy signal", () => {
    expect(
      metaMatchesDeploy({ containerId: "shared-v18" }, expectedContainerId(SHORT_REV)),
    ).toBe(false);
  });

  it("rejects a missing, empty or unrelated meta payload", () => {
    for (const meta of [null, undefined, {}, { containerId: null }, { containerId: "" }]) {
      expect(metaMatchesDeploy(meta, expectedContainerId(SHORT_REV))).toBe(false);
    }
  });

  it("does not accept a substring or prefix of the expected id", () => {
    const expected = expectedContainerId(SHORT_REV);
    expect(metaMatchesDeploy({ containerId: expected.slice(0, -1) }, expected)).toBe(false);
    expect(metaMatchesDeploy({ containerId: `${expected}0` }, expected)).toBe(false);
  });
});

describe("metaMatchesDigichat (the digichat id field)", () => {
  it("names the digichat field explicitly and reuses the shared field-aware matcher", () => {
    // Control that makes the wrong-field arms meaningful: the two fields are
    // different keys and the matcher is the shared module's, parameterised on
    // the field rather than a second copy.
    expect(META_FIELD).toBe("digichatContainerId");
    expect(META_URL).toContain("_stack/meta");
    expect(metaMatchesDigichat({
      digichatContainerId: sharedDigichatContainerId(SHORT_REV),
    }, sharedDigichatContainerId(SHORT_REV))).toBe(true);
    expect(sharedMetaFieldMatches({ digichatContainerId: sharedDigichatContainerId(SHORT_REV) }, sharedDigichatContainerId(SHORT_REV), META_FIELD)).toBe(true);
  });

  it("passes only when digichatContainerId matches, even though containerId does not", () => {
    // A realistic `/_stack/meta`: the digichat id is right, the stack's
    // own value is deliberately different. A wrapper that read the wrong key
    // would report failure here.
    const meta = {
      containerId: sharedStackContainerId("111111111111"),
      digichatContainerId: sharedDigichatContainerId(SHORT_REV),
      digichatRev: SHORT_REV,
    };
    expect(metaMatchesDigichat(meta, sharedDigichatContainerId(SHORT_REV))).toBe(true);
  });

  it("refuses a payload that reports only the stack's own id", () => {
    // THE DISCRIMINATING ARM: `containerId` present and plausible,
    // `digichatContainerId` absent. It must not read as verified.
    const meta = { containerId: sharedStackContainerId(SHORT_REV) };
    expect(metaMatchesDigichat(meta, sharedDigichatContainerId(SHORT_REV))).toBe(false);
  });

  it("refuses when the digichat id is stale", () => {
    const meta = {
      containerId: sharedStackContainerId(SHORT_REV),
      digichatContainerId: "shared-v10",
      digichatRev: null,
    };
    expect(metaMatchesDigichat(meta, sharedDigichatContainerId(SHORT_REV))).toBe(false);
  });

  it("treats an unreadable route as unproven, never as a pass", () => {
    for (const meta of [null, undefined, {}, { digichatContainerId: null }]) {
      expect(metaMatchesDigichat(meta, sharedDigichatContainerId(SHORT_REV))).toBe(false);
    }
  });

  it("both fields together are required: one match alone is not a deploy proof", () => {
    const expected = expectedContainerId(SHORT_REV);
    const partial = { containerId: expected }; // digichat id missing
    expect(metaMatchesDeploy(partial, expected)).toBe(true);
    expect(metaMatchesDigichat(partial, expected)).toBe(false);
  });
});
