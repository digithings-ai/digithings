/**
 * GET /healthz — auth-exempt liveness, always `{"ok": true}` in every
 * license state. Never consults license state.
 */

import { describe, expect, it } from "vitest";
import { GET } from "./route";
import {
  applyHeartbeatResult,
  resetLicenseStateForTests,
} from "@/lib/license/state";

describe("GET /healthz", () => {
  it("answers {ok:true} with 200 while unlicensed", async () => {
    resetLicenseStateForTests();
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
    resetLicenseStateForTests();
  });

  it("answers {ok:true} with 200 while revoked and expired", async () => {
    resetLicenseStateForTests();
    try {
      applyHeartbeatResult("denied", "heartbeat_deny_revoked");
      expect((await (await GET()).json())).toEqual({ ok: true });
      expect((await GET()).status).toBe(200);
      resetLicenseStateForTests();
      applyHeartbeatResult("expired");
      expect((await (await GET()).json())).toEqual({ ok: true });
      expect((await GET()).status).toBe(200);
    } finally {
      resetLicenseStateForTests();
    }
  });
});
