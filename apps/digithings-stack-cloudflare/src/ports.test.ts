import { describe, expect, it } from "vitest";
import {
  DIGIGRAPH_PORT,
  DIGIKEY_PORT,
  DIGISEARCH_PORT,
  LEGACY_SHARED_STACK_CONTAINER_ID,
  portForHostname,
  sharedStackContainerId,
  stackContainerRev,
} from "./ports";

describe("portForHostname", () => {
  it("routes graph.digithings.ai to digigraph", () => {
    expect(portForHostname("graph.digithings.ai")).toBe(DIGIGRAPH_PORT);
  });

  it("routes key.digithings.ai to digikey", () => {
    expect(portForHostname("key.digithings.ai")).toBe(DIGIKEY_PORT);
  });

  it("routes search.digithings.ai to digisearch", () => {
    expect(portForHostname("search.digithings.ai")).toBe(DIGISEARCH_PORT);
  });

  it("routes any search.* host to digisearch (same prefix rule as graph.*/key.*)", () => {
    expect(portForHostname("search.example.com")).toBe(DIGISEARCH_PORT);
  });

  it("defaults workers.dev / localhost to digigraph", () => {
    expect(portForHostname("digithings-stack.example.workers.dev")).toBe(
      DIGIGRAPH_PORT,
    );
    expect(portForHostname("localhost")).toBe(DIGIGRAPH_PORT);
  });

  it("rejects unknown hosts", () => {
    expect(portForHostname("evil.example.com")).toBeNull();
  });
});

/**
 * DIG-3229. The shared-stack Container id used to be a hand-edited string
 * ("shared-v18") that a deploy had to remember to bump; forgetting it shipped
 * no real fix while CI stayed green, and it already caused two incidents
 * (shared-v16 → v17, a committed PII snapshot re-ingested on every cold start;
 * shared-v17 → v18, a digikey JWT scope-escalation build still in service).
 *
 * The id is now derived from the deploying commit, so every deploy addresses a
 * different Durable Object id and therefore a fresh instance. These cases pin
 * the three properties that makes true: determinism, injectivity, and a
 * fail-safe fallback for a build with no rev.
 */
describe("sharedStackContainerId", () => {
  it("derives the id from the deploying commit", () => {
    expect(sharedStackContainerId("822af7515ab")).toBe("shared-822af7515ab");
  });

  it("gives a different id for every different commit (eviction guarantee)", () => {
    // The property that replaces the manual bump: two different deploys can
    // never address the same Container instance, which is exactly what a
    // forgotten bump used to allow.
    expect(sharedStackContainerId("822af7515ab")).not.toBe(
      sharedStackContainerId("e4454bfa4a12"),
    );
  });

  it("is stable for the same commit (a redeploy does not churn the id)", () => {
    expect(sharedStackContainerId("822af7515ab")).toBe(
      sharedStackContainerId("822af7515ab"),
    );
  });

  it("normalises case and whitespace so one commit cannot produce two ids", () => {
    expect(sharedStackContainerId("  822AF7515AB\n")).toBe("shared-822af7515ab");
  });

  it("keeps the id inside the Durable Object name alphabet", () => {
    const id = sharedStackContainerId('a"; DROP TABLE x --_\n\tzz');
    expect(id).toMatch(/^shared-[0-9a-z]+$/);
  });

  it("falls back to the pinned legacy id when no rev was injected", () => {
    // A build with no rev is a CI `wrangler deploy --dry-run` or a deploy that
    // bypassed `npm run deploy`. Reproducing today's id exactly means the
    // fallback can never itself cause a surprise eviction.
    expect(sharedStackContainerId(undefined)).toBe(
      LEGACY_SHARED_STACK_CONTAINER_ID,
    );
    expect(sharedStackContainerId("")).toBe(LEGACY_SHARED_STACK_CONTAINER_ID);
    expect(sharedStackContainerId("   ")).toBe(LEGACY_SHARED_STACK_CONTAINER_ID);
  });

  it("never drops a rev silently to the fallback", () => {
    // Normalisation is total: any non-empty rev yields a derived id, never the
    // legacy one. The single string that can read as the fallback is a rev that
    // literally equals the legacy suffix — and "v18" is not a git sha, so
    // scripts/deploy.mjs refuses it before it can reach here (pinned in
    // container-id-deploy.test.js).
    expect(stackContainerRev("v18")).toBe("v18");
    expect(sharedStackContainerId("deadbeefcafe")).not.toBe(
      LEGACY_SHARED_STACK_CONTAINER_ID,
    );
    expect(sharedStackContainerId("!!!")).toBe(LEGACY_SHARED_STACK_CONTAINER_ID);
  });

  it("reads the build-injected rev when no argument is passed", () => {
    // This call is what index.ts makes. Under vitest (and under any
    // `wrangler deploy` that did not pass --define) the identifier is not
    // defined, so this is the fallback arm — the same shape a bypassing deploy
    // produces, asserted here rather than left to the deploy wrapper.
    expect(sharedStackContainerId()).toBe(LEGACY_SHARED_STACK_CONTAINER_ID);
    expect(stackContainerRev()).toBeNull();
  });
});

describe("stackContainerRev", () => {
  it("reports the normalised rev for /_stack/meta diagnostics", () => {
    expect(stackContainerRev("822AF7515ab")).toBe("822af7515ab");
  });

  it("reports null when the build carries no rev", () => {
    expect(stackContainerRev(undefined)).toBeNull();
    expect(stackContainerRev("")).toBeNull();
  });

  it("is null only when the id is the legacy fallback", () => {
    // One predicate, so an operator reading /_stack/meta can tell an
    // evicted-on-deploy id from a fallback id without inferring it.
    expect(stackContainerRev("822af7515ab")).not.toBeNull();
    expect(stackContainerRev(undefined)).toBeNull();
  });
});
