/**
 * The deploy wrapper is the only thing that carries the rev, so its contract is
 * the contract. Three properties are pinned here, and each is paired with a
 * control that fires, because a green assertion on this file is worthless
 * unless the reader can see the matcher working:
 *
 *   1. FAIL CLOSED. Every way `git rev-parse` can come back short of a usable
 *      sha refuses the deploy. No branch defaults to "deploy anyway".
 *   2. THE REV ALWAYS TRAVELS. There is no argv shape, including with extra
 *      wrangler args, that omits the var. This is the property the ticket
 *      rests on: if a rev-less deploy is expressible, the hole is open again.
 *   3. THIS FILE AND paths.ts AGREE. The wrapper's `expectedContainerId` and
 *      `REV_VAR` are re-derived here and compared against the real module. A
 *      rename on either side fails here rather than shipping a deploy that
 *      writes a var nobody reads, or verifies an id nobody serves.
 *
 * `.js` on purpose, mirroring the sibling package: this test imports a plain
 * `.mjs` that has no TypeScript declarations, so a `.ts` test would be red with
 * TS7016 against a hand-written `.d.ts` that could itself drift. `vitest.config.ts`
 * collects both extensions and `tsconfig.json` includes only `*.ts`, so a `.js`
 * test is collected by the suite and invisible to `tsc --noEmit`.
 *
 * Lives in digichat (not the fold) because both halves of the equality — the
 * wrapper and the derivation — are in this package. The fold's own equality
 * with the standalone Worker is pinned separately in
 * `apps/digithings-stack-cloudflare/src/digichat-mount.test.js`.
 */
import { describe, expect, it } from "vitest";
import {
  EXIT_DEPLOYED_UNVERIFIED,
  META_URL,
  REV_LEN,
  REV_VAR,
  SHA_RE,
  buildVarArg,
  buildWranglerArgs,
  expectedContainerId,
  metaMatchesDeploy,
  resolveDeployRev,
  verdictFor,
} from "../scripts/deploy.mjs";
import {
  DIGICHAT_CONTAINER_REV_VAR,
  LEGACY_SHARED_DIGICHAT_CONTAINER_ID,
  digichatContainerRev,
  sharedDigichatContainerId,
} from "./paths.ts";

const REAL_SHA = "3528cf9f7ab1c2d3e4f5061728394a5b6c7d8e9f";

describe("sha shape (the gate every rev must pass)", () => {
  it("accepts a real sha and refuses everything else", () => {
    // Control: the positive arm, so a zero below is the needle, not the matcher.
    expect(SHA_RE.test(REAL_SHA)).toBe(true);
    expect(SHA_RE.test("3528cf9")).toBe(true);
    expect(SHA_RE.test("3528CF9F")).toBe(false); // uppercase: git emits lowercase
    expect(SHA_RE.test("3528cf")).toBe(false); // 6 chars: too short to pin a deploy
    expect(SHA_RE.test("../../etc/passwd")).toBe(false);
    expect(SHA_RE.test("")).toBe(false);
    expect(SHA_RE.test("shared-v10")).toBe(false);
  });
});

describe("resolveDeployRev fails closed", () => {
  it("returns a 12-char rev from a 40-char sha", () => {
    const rev = resolveDeployRev(() => ({ status: 0, stdout: `${REAL_SHA}\n` }));
    expect(rev).toBe(REAL_SHA.slice(0, REV_LEN));
    expect(rev).toHaveLength(12);
  });

  it("refuses every shortcoming, and says which one", () => {
    const arms = [
      ["git failed", () => ({ status: 128, stdout: "", stderr: "not a git repository" })],
      ["empty stdout", () => ({ status: 0, stdout: "   \n" })],
      ["stdout is not a sha", () => ({ status: 0, stdout: "main\n" })],
      ["spawnSync returned nothing at all", () => undefined],
    ];
    for (const [label, runGit] of arms) {
      let thrown = null;
      try {
        resolveDeployRev(runGit);
      } catch (err) {
        thrown = err;
      }
      expect(thrown, `arm "${label}" must refuse, not default`).not.toBeNull();
      expect(thrown.message).toContain("REFUSED");
    }
  });

  it("does resolve a rev on the happy arm, so the refusals are refusals", () => {
    // Control: without this the arms above could pass on a function that always throws.
    expect(typeof resolveDeployRev(() => ({ status: 0, stdout: REAL_SHA }))).toBe("string");
  });
});

describe("the rev always travels with the deploy", () => {
  it("builds exactly one --var, colon-separated, unquoted", () => {
    expect(buildVarArg("3528cf9f7ab1")).toBe(`--var=${REV_VAR}:3528cf9f7ab1`);
  });

  it("refuses to build a var from anything that is not a sha", () => {
    for (const bad of ["", "main", "3528CF9F7AB1", "../../etc", null, 42]) {
      expect(() => buildVarArg(bad), `arm ${JSON.stringify(bad)}`).toThrow(/REFUSED/);
    }
  });

  it("has no argv shape that omits the rev, with or without extra args", () => {
    const rev = "3528cf9f7ab1";
    const shapes = [
      buildWranglerArgs(rev),
      buildWranglerArgs(rev, []),
      buildWranglerArgs(rev, ["--containers-rollout=none"]),
      buildWranglerArgs(rev, ["--outdir", "/tmp/x"]),
    ];
    for (const argv of shapes) {
      const revArgs = argv.filter((a) => a.startsWith("--var="));
      expect(revArgs).toEqual([`--var=${REV_VAR}:${rev}`]);
      expect(argv.slice(0, 4)).toEqual(["exec", "--", "wrangler", "deploy"]);
    }
  });
});

describe("this file and paths.ts agree (one derivation, two surfaces)", () => {
  it("uses the same Worker var name as the derivation reads", () => {
    // Control: both names are non-empty, so a rename to "" on both sides could
    // not satisfy this by being empty twice.
    expect(REV_VAR).toBe("DIGICHAT_CONTAINER_REV");
    expect(DIGICHAT_CONTAINER_REV_VAR).toBe("DIGICHAT_CONTAINER_REV");
    expect(REV_VAR).toBe(DIGICHAT_CONTAINER_REV_VAR);
  });

  it("computes the same id the Worker will compute, for every rev", () => {
    for (const rev of ["3528cf9f7ab1", "0123456789ab", "abcdef012345", "fedcba987654"]) {
      expect(expectedContainerId(rev)).toBe(`shared-${rev}`);
      expect(sharedDigichatContainerId(rev)).toBe(expectedContainerId(rev));
    }
    // Control: the derivation really consumes the rev — it is not a constant
    // returning the same string for every input.
    const ids = new Set(
      ["3528cf9f7ab1", "0123456789ab", "abcdef012345"].map((r) => sharedDigichatContainerId(r)),
    );
    expect(ids.size).toBe(3);
  });

  it("falls back to the legacy id when no rev arrives, and that id is distinguishable", () => {
    // A rev-less deploy is the failure this ticket exists to prevent, so the
    // fallback is deliberate (a rollback from a commit that predates the
    // derivation still has to boot something) rather than an error. What has to
    // hold is that the fallback is NOT any id a rev could produce — that is
    // what makes a missing rev detectable by the post-deploy read.
    for (const absent of [undefined, null, "", "   "]) {
      expect(digichatContainerRev(absent)).toBeNull();
      expect(sharedDigichatContainerId(absent)).toBe(LEGACY_SHARED_DIGICHAT_CONTAINER_ID);
    }
    // Control: the fallback is reachable and the rev path is live, so this is a
    // real branch and not an assertion that holds because both sides are empty.
    expect(LEGACY_SHARED_DIGICHAT_CONTAINER_ID).toMatch(/^shared-/);
    const revIds = ["3528cf9f7ab1", "0123456789ab", "abcdef012345"].map((r) =>
      sharedDigichatContainerId(r),
    );
    expect(revIds).not.toContain(LEGACY_SHARED_DIGICHAT_CONTAINER_ID);
    expect(sharedDigichatContainerId("3528cf9f7ab1")).not.toBe(
      sharedDigichatContainerId(undefined),
    );
  });
});

describe("post-deploy verdict", () => {
  it("exits 0 only when the deployed id is the one this commit implies", () => {
    const expected = expectedContainerId("3528cf9f7ab1");
    const good = verdictFor({
      meta: { containerId: expected, rev: "3528cf9f7ab1" },
      expected,
      metaUrl: META_URL,
      readError: null,
    });
    expect(good.exitCode).toBe(0);
    expect(metaMatchesDeploy({ containerId: expected }, expected)).toBe(true);
    // Control: the matcher discriminates.
    expect(metaMatchesDeploy({ containerId: "shared-v10" }, expected)).toBe(false);
    expect(metaMatchesDeploy(null, expected)).toBe(false);
    expect(metaMatchesDeploy({}, expected)).toBe(false);
  });

  it("distinguishes 'deployed but the id is wrong' from 'deployed, nothing to read'", () => {
    const expected = expectedContainerId("3528cf9f7ab1");

    const reachableButWrong = verdictFor({
      meta: { containerId: "shared-v10", rev: null },
      expected,
      metaUrl: META_URL,
      readError: null,
    });
    expect(reachableButWrong.exitCode).toBe(EXIT_DEPLOYED_UNVERIFIED);
    expect(reachableButWrong.message).toContain("legacy id here means");

    const notVerifiable = verdictFor({
      meta: null,
      expected,
      metaUrl: META_URL,
      readError: "HTTP 404",
    });
    expect(notVerifiable.exitCode).toBe(EXIT_DEPLOYED_UNVERIFIED);
    expect(notVerifiable.message).toContain("no zone route");
  });

  it("never reports verified when the id does not match", () => {
    const expected = expectedContainerId("3528cf9f7ab1");
    const metas = [null, {}, { containerId: null }, { containerId: "shared-zzzzzzzzzzzz" }];
    const readErrors = [null, undefined, "HTTP 404", "ECONNREFUSED"];
    for (const meta of metas) {
      for (const readError of readErrors) {
        const v = verdictFor({ meta, expected, metaUrl: META_URL, readError });
        expect(v.exitCode).toBe(EXIT_DEPLOYED_UNVERIFIED);
        expect(v.exitCode).not.toBe(0);
      }
    }
  });

  it("uses an exit code distinct from wrangler's own non-zero", () => {
    expect(EXIT_DEPLOYED_UNVERIFIED).toBe(2);
  });
});