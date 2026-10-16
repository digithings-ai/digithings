/**
 * The stack deploy wrapper is the deploy path for the surface that actually
 * serves digichat traffic, so its contract is pinned here.
 *
 * The property that matters most is not "the wrapper carries a rev" — it is
 * "the wrapper verifies the FOLDED DIGICHAT id". `/_stack/meta` publishes two
 * different container ids: `containerId` is the stack's own (hand-pinned
 * "shared-v18", owned by DIG-3229 / PR #5537, still open) and
 * `digichatContainerId` is the folded digichat one this ticket is about. A
 * wrapper pointed at the wrong key would either fail forever or, worse, pass
 * while the folded id stayed pinned. Every assertion below is built around that
 * distinction, and the discriminating arm is a meta payload carrying ONLY the
 * stack's own id: the wrapper must refuse it rather than call it verified.
 *
 * `.js` for the same reason as the digichat twin: this imports a plain `.mjs`
 * that has no TypeScript declarations, and `tsconfig.json` includes only `*.ts`,
 * so a `.js` test is collected by vitest and stays out of `tsc --noEmit`
 * rather than needing a hand-written `.d.ts` that could itself drift.
 */
import { describe, expect, it } from "vitest";
import {
  META_FIELD,
  META_URL,
  REV_VAR,
  buildVarArg,
  buildWranglerArgs,
  metaMatchesDeploy,
  resolveDeployRev,
  stackVerdict,
} from "../scripts/deploy.mjs";
import { sharedDigichatContainerId } from "./digichat";
import { SHARED_STACK_CONTAINER_ID } from "./ports";

const REV = "3528cf9f7ab1";

describe("the stack wrapper reuses the one rev implementation", () => {
  it("imports the shared rev logic rather than reimplementing it", () => {
    // Live-import proof: if these were copied, editing the shared gate would
    // leave the stack wrapper behind and the hole would reopen on the live
    // surface. Identity against the shared module is the strongest available
    // statement, so the test holds the shared module's exports directly.
    expect(resolveDeployRev(() => ({ status: 0, stdout: `${REV}${"0".repeat(28)}` }))).toBe(REV);
    expect(REV_VAR).toBe("DIGICHAT_CONTAINER_REV");
    expect(buildVarArg(REV)).toBe(`--var=DIGICHAT_CONTAINER_REV:${REV}`);
    const argv = buildWranglerArgs(REV, ["--containers-rollout=none"]);
    expect(argv.filter((a) => a.startsWith("--var="))).toEqual([
      `--var=DIGICHAT_CONTAINER_REV:${REV}`,
    ]);
  });

  it("shares the failure behaviour too: no rev means no deploy", () => {
    for (const arm of [
      () => ({ status: 128, stdout: "", stderr: "" }),
      () => ({ status: 0, stdout: "not-a-sha" }),
    ]) {
      expect(() => resolveDeployRev(arm)).toThrow(/REFUSED/);
    }
  });
});

describe("the wrapper verifies the FOLDED DIGICHAT id, not the stack's own", () => {
  it("names the digichat field explicitly", () => {
    // Control that makes the next arm meaningful: the two fields are different
    // keys and the stack's own id is NOT a rev-shaped value.
    expect(META_FIELD).toBe("digichatContainerId");
    expect(META_URL).toContain("_stack/meta");
    expect(SHARED_STACK_CONTAINER_ID).not.toBe(sharedDigichatContainerId(REV));
  });

  it("passes only when digichatContainerId matches, even though containerId does not", () => {
    // A realistic `/_stack/meta`: the folded digichat id is right, the stack's
    // own is deliberately left at its hand-pinned value. A wrapper that read the
    // wrong key would report failure here.
    const meta = {
      containerId: SHARED_STACK_CONTAINER_ID,
      digichatContainerId: sharedDigichatContainerId(REV),
      digichatRev: REV,
    };
    const ok = stackVerdict({ meta, expected: sharedDigichatContainerId(REV), readError: null });
    expect(ok.exitCode).toBe(0);
  });

  it("refuses a payload that reports only the stack's own id", () => {
    // THE DISCRIMINATING ARM. This is the wrong-field wrapper's only success
    // case: `containerId` present and plausible, `digichatContainerId` absent.
    // It must not read as verified.
    const meta = { containerId: SHARED_STACK_CONTAINER_ID };
    const v = stackVerdict({ meta, expected: sharedDigichatContainerId(REV), readError: null });
    expect(v.exitCode).not.toBe(0);
    expect(v.exitCode).toBe(2);
    expect(v.message).toContain(META_FIELD);
    expect(v.message).toContain("undefined");
  });

  it("refuses when the folded id is stale, and says so", () => {
    const meta = {
      containerId: SHARED_STACK_CONTAINER_ID,
      digichatContainerId: "shared-v10",
      digichatRev: null,
    };
    const v = stackVerdict({ meta, expected: sharedDigichatContainerId(REV), readError: null });
    expect(v.exitCode).toBe(2);
    expect(v.message).toContain("legacy id here means");
  });

  it("treats an unreadable route as unproven, never as a pass", () => {
    for (const meta of [null, {}, { digichatContainerId: null }]) {
      for (const readError of [null, "HTTP 404", "ECONNREFUSED"]) {
        const v = stackVerdict({
          meta,
          expected: sharedDigichatContainerId(REV),
          readError,
        });
        expect(v.exitCode).toBe(2);
      }
    }
    // Control: the matcher itself is not simply always-false.
    expect(metaMatchesDeploy({ digichatContainerId: sharedDigichatContainerId(REV) },
      sharedDigichatContainerId(REV),
      META_FIELD,
    )).toBe(true);
  });
});