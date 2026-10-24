import { beforeEach, describe, expect, it } from "vitest";
import {
  activeSessionCount,
  bindLink,
  endSession,
  isLiveSessionLink,
  registerSession,
  resetSessionLinks,
} from "./session-links";

/**
 * The two cases the decision on DIG-2638 names explicitly: a reload and a new
 * session must both kill the link. There is no TTL here on purpose, so these
 * tests are the only thing that could regress it into one.
 */
describe("session-scoped artifact links", () => {
  beforeEach(() => resetSessionLinks());

  it("a link bound to a live session validates", () => {
    registerSession("conv-1");
    expect(bindLink("conv-1", "artifact-token-a")).toBe(true);
    expect(isLiveSessionLink("conv-1", "artifact-token-a")).toBe(true);
  });

  it("a link does not validate for a session that was never registered", () => {
    expect(bindLink("conv-ghost", "artifact-token-a")).toBe(false);
    expect(isLiveSessionLink("conv-ghost", "artifact-token-a")).toBe(false);
  });

  it("ending the session kills every link it minted", () => {
    registerSession("conv-1");
    bindLink("conv-1", "artifact-token-a");
    bindLink("conv-1", "artifact-token-b");
    endSession("conv-1");
    expect(isLiveSessionLink("conv-1", "artifact-token-a")).toBe(false);
    expect(isLiveSessionLink("conv-1", "artifact-token-b")).toBe(false);
    expect(activeSessionCount()).toBe(0);
  });

  it("a reload under a new session id kills the old session's links", () => {
    registerSession("conv-1", "client-1");
    bindLink("conv-1", "artifact-token-a");
    // Reload: the same client comes back under a fresh session id.
    registerSession("conv-2", "client-1");
    bindLink("conv-2", "artifact-token-a");
    expect(isLiveSessionLink("conv-1", "artifact-token-a")).toBe(false);
    expect(isLiveSessionLink("conv-2", "artifact-token-a")).toBe(true);
    expect(activeSessionCount()).toBe(1);
  });

  it("without a client key a second session does not disturb the first", () => {
    // Sessions are only related when the caller says they are, so an unrelated
    // conversation is never able to end someone else's session.
    registerSession("conv-1");
    bindLink("conv-1", "artifact-token-a");
    registerSession("conv-2");
    expect(isLiveSessionLink("conv-1", "artifact-token-a")).toBe(true);
  });

  it("a second client is unaffected by the first client's reload", () => {
    registerSession("conv-a", "client-a");
    bindLink("conv-a", "token-a");
    registerSession("conv-b", "client-b");
    bindLink("conv-b", "token-b");
    registerSession("conv-c", "client-a");
    expect(isLiveSessionLink("conv-a", "token-a")).toBe(false);
    expect(isLiveSessionLink("conv-b", "token-b")).toBe(true);
    expect(activeSessionCount()).toBe(2);
  });

  it("re-registering the same session keeps its token and links", () => {
    const first = registerSession("conv-1", "client-1");
    bindLink("conv-1", "artifact-token-a");
    const second = registerSession("conv-1", "client-1");
    expect(second).toBe(first);
    expect(isLiveSessionLink("conv-1", "artifact-token-a")).toBe(true);
  });

  it("two sessions for one client never share a link token", () => {
    registerSession("conv-1", "client-1");
    registerSession("conv-2", "client-1");
    expect(registerSession("conv-2", "client-1")).not.toBe(registerSession("conv-1", "client-1"));
  });

  it("a link from another session does not validate, even with the right token", () => {
    registerSession("conv-1");
    registerSession("conv-2");
    bindLink("conv-1", "artifact-token-a");
    expect(isLiveSessionLink("conv-2", "artifact-token-a")).toBe(false);
  });

  it("a token of a different length never validates", () => {
    registerSession("conv-1");
    bindLink("conv-1", "short");
    expect(isLiveSessionLink("conv-1", "short-but-longer")).toBe(false);
  });
});
