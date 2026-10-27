import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  loadDigichatConfig,
  resetDigichatConfigForTests,
  setDigichatConfigForTests,
} from "@/lib/deploy-config/loader";
import { GET } from "./route";

/** A test fixture, not a credential. */
const INVITE = "invite-fixture-not-a-secret";
const INVITE_HOST = "occ.digithings.ai";

function chrome(host: string | null, headers: Record<string, string> = {}): Request {
  const url = new URL("https://digithings.ai/chat/api/deploy/chrome");
  if (host) url.searchParams.set("host", host);
  return new Request(url, { headers });
}

describe("GET /api/deploy/chrome (DIG-3585)", () => {
  beforeEach(() => {
    setDigichatConfigForTests(
      loadDigichatConfig({
        fileContents: [
          "version: 1",
          "hosts:",
          "  digithings.ai:",
          "    slug: digithings-ai",
          "    backend: { type: digigraph }",
          "    chrome: { title: House }",
          `  ${INVITE_HOST}:`,
          "    slug: occ",
          `    token: ${INVITE}`,
          "    backend: { type: digigraph }",
          "    chrome: { title: Invite tenant }",
          "",
        ].join("\n"),
        env: {},
      }),
    );
  });

  afterEach(() => {
    resetDigichatConfigForTests();
  });

  it("answers 404 for an invite-only host without its token", async () => {
    for (const headers of [{}, { "x-embed-token": "guess" }, { origin: `https://${INVITE_HOST}` }]) {
      const res = await GET(chrome(INVITE_HOST, headers));
      expect(res.status).toBe(404);
      expect(await res.text()).not.toMatch(/Invite tenant|"occ"/);
    }
  });

  it("never reads the token from the query string", async () => {
    const url = new URL("https://digithings.ai/chat/api/deploy/chrome");
    url.searchParams.set("host", INVITE_HOST);
    url.searchParams.set("token", INVITE);
    expect((await GET(new Request(url))).status).toBe(404);
  });

  it("serves the invite-only chrome with the token the edge binds", async () => {
    const res = await GET(chrome(INVITE_HOST, { "x-embed-token": INVITE }));
    expect(res.status).toBe(200);
    const body = (await res.json()) as { slug?: string; title?: string };
    expect(body.slug).toBe("occ");
    expect(JSON.stringify(body)).not.toContain(INVITE);
  });

  it("still serves the house chrome without a token", async () => {
    for (const host of ["digithings.ai", null]) {
      const res = await GET(chrome(host));
      expect(res.status).toBe(200);
      expect(((await res.json()) as { slug?: string }).slug).toBe("digithings-ai");
    }
  });
});
