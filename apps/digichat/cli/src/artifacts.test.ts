import { describe, expect, it, vi } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  ARTIFACTS_COMMAND_HINT,
  ARTIFACTS_COMMAND_NAME,
  ARTIFACTS_DISPATCH_DOWNLOADED,
  ARTIFACTS_DISPATCH_OPENED,
  CliArtifactRequestError,
  artifactsAvailable,
  artifactBlobUrl,
  artifactListUrl,
  conversationCreateUrl,
  ensureConversation,
  listSessionArtifacts,
  openArtifact,
  openArtifactAt,
  nextArtifactIndex,
} from "./artifacts.js";
import type { CliArtifactRow } from "./artifacts.js";
import type { DigichatCliAuth } from "./chat-request.js";

const API_KEY: DigichatCliAuth = { kind: "api_key", apiKey: "digi_live_test_key" };
const BASE = "https://digichat.example.com";
const CONVERSATION = "11111111-2222-3333-4444-555555555555";

/** Repo root = the nearest ancestor holding `packages/digichat-ui`. Resolved from cwd. */
function repoRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 8; i += 1) {
    if (existsSync(resolve(dir, "packages/digichat-ui/src/slash-commands.ts"))) return dir;
    const parent = resolve(dir, "..");
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error("repo root not found from cwd - the conformance tests below cannot pass vacuously");
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const row = (over: Partial<CliArtifactRow> = {}): CliArtifactRow => ({
  id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  token: "tok-1",
  name: "chart.png",
  mediaType: "image/png",
  byteSize: 2048,
  kind: "image",
  summary: null,
  createdAt: "2026-10-11T09:00:00.000Z",
  viewable: true,
  ...over,
});

describe("artifacts availability mirrors the web session-store gate", () => {
  it("is offered for a digichat machine key", () => {
    expect(artifactsAvailable(API_KEY)).toBe(true);
  });

  // Same decision the web embed client makes with `hasArtifacts: false`: without an
  // authenticated session store the route cannot be reached, so the command is not offered.
  it.each([
    [{ kind: "embed", token: "t", host: "digithings.ai" }, "embed"],
    [{ kind: "none" }, "none"],
  ] as const)("is not offered for %s auth (%s)", (auth, label) => {
    expect(artifactsAvailable(auth)).toBe(false);
    expect(label).toMatch(/embed|none/);
  });
});

describe("conversation creation uses the store's own client-chosen id", () => {
  it("POSTs the id once and returns it", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return jsonResponse({ id: CONVERSATION }, 201);
    });

    const created = await ensureConversation({
      baseUrl: BASE,
      auth: API_KEY,
      conversationId: CONVERSATION,
      title: "digichat",
      fetchImpl,
    });

    expect(created).toBe(true);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe(conversationCreateUrl(BASE));
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({
      id: CONVERSATION,
      title: "digichat",
    });
  });

  it("refuses without a machine key before any request", async () => {
    const fetchImpl = vi.fn();
    await expect(
      ensureConversation({
        baseUrl: BASE,
        auth: { kind: "none" },
        conversationId: CONVERSATION,
        fetchImpl: fetchImpl as never,
      }),
    ).rejects.toBeInstanceOf(CliArtifactRequestError);
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});

describe("listing", () => {
  it("requests the web list route with the machine key and returns the server rows", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ artifacts: [row(), row({ token: "tok-2", viewable: false })] }),
    );

    const rows = await listSessionArtifacts({
      baseUrl: BASE,
      auth: API_KEY,
      conversationId: CONVERSATION,
      fetchImpl,
    });

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(artifactListUrl(BASE, CONVERSATION));
    const headers = init.headers as Record<string, string>;
    expect(headers.authorization).toBe("Bearer digi_live_test_key");
    expect(headers["x-digi-caller"]).toBe("digichat-cli");
    expect(rows).toHaveLength(2);
    // The server's flag survives untouched; the TUI never recomputes it.
    expect(rows.map((r) => r.viewable)).toEqual([true, false]);
  });

  it("never touches the network without a machine key", async () => {
    const fetchImpl = vi.fn();
    await expect(
      listSessionArtifacts({
        baseUrl: BASE,
        auth: { kind: "embed", token: "t" },
        conversationId: CONVERSATION,
        fetchImpl: fetchImpl as never,
      }),
    ).rejects.toBeInstanceOf(CliArtifactRequestError);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("surfaces the status so the panel can say what happened", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ error: "unauthorized" }, 401));
    const error = await listSessionArtifacts({
      baseUrl: BASE,
      auth: API_KEY,
      conversationId: CONVERSATION,
      fetchImpl,
    }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(CliArtifactRequestError);
    expect((error as CliArtifactRequestError).status).toBe(401);
  });
});

describe("open/download dispatch - the non-vacuity control", () => {
  // Both rows carry the SAME mediaType and differ only in the server's `viewable`.
  // A TUI-side media-type list cannot produce that split, so this pair kills any mutant
  // that re-decides the behaviour locally or always downloads.
  it("splits on the server flag alone", async () => {
    const openInOs = vi.fn();
    const download = vi.fn();
    const rows = [row({ token: "inline", mediaType: "image/png", viewable: true }),
                  row({ token: "file", mediaType: "image/png", viewable: false })];

    await expect(openArtifactAt(rows, 0, { baseUrl: BASE, conversationId: CONVERSATION, openInOs, download }))
      .resolves.toBe(ARTIFACTS_DISPATCH_OPENED);
    expect(openInOs).toHaveBeenCalledTimes(1);
    expect(download).toHaveBeenCalledTimes(0);
    expect(openInOs.mock.calls[0][0]).toBe(
      artifactBlobUrl(BASE, CONVERSATION, "inline"),
    );

    await expect(openArtifactAt(rows, 1, { baseUrl: BASE, conversationId: CONVERSATION, openInOs, download }))
      .resolves.toBe(ARTIFACTS_DISPATCH_DOWNLOADED);
    expect(download).toHaveBeenCalledTimes(1);
    expect(openInOs).toHaveBeenCalledTimes(1);
    expect(download.mock.calls[0][0]).toBe(
      artifactBlobUrl(BASE, CONVERSATION, "file"),
    );
  });

  it("does not re-decide viewability from the media type", async () => {
    const openInOs = vi.fn();
    const download = vi.fn();
    // `text/*` and `application/json` are viewable on the server, so a local list would
    // open these. The server said false; the TUI must download.
    for (const mediaType of ["text/plain", "application/json", "image/png"]) {
      await expect(
        openArtifact(row({ mediaType, viewable: false }), {
          baseUrl: BASE,
          conversationId: CONVERSATION,
          openInOs,
          download,
        }),
      ).resolves.toBe(ARTIFACTS_DISPATCH_DOWNLOADED);
    }
    expect(openInOs).not.toHaveBeenCalled();
    expect(download).toHaveBeenCalledTimes(3);
  });

  it("routes through the row the panel hands it, not through a re-fetch", async () => {
    const openInOs = vi.fn();
    const download = vi.fn();
    const target = row({ token: "picked", viewable: true });
    await expect(
      openArtifact(target, {
        baseUrl: BASE,
        conversationId: CONVERSATION,
        openInOs,
        download,
      }),
    ).resolves.toBe(ARTIFACTS_DISPATCH_OPENED);
    expect(openInOs.mock.calls[0][0]).toContain("token=picked");
    expect(download).not.toHaveBeenCalled();
  });
});

describe("parity with the web leaf - source conformance, no duplicate registry", () => {
  it("uses the command name and hint the shared slash registry defines", () => {
    const src = readFileSync(
      resolve(repoRoot(), "packages/digichat-ui/src/slash-commands.ts"),
      "utf8",
    );
    // Firing control: the matcher must find a known def too, or every assert below is vacuous.
    expect(src).toContain('names: ["/websearch"]');
    expect(src).toContain(`id: "artifacts"`);
    expect(src).toContain(`names: ["${ARTIFACTS_COMMAND_NAME}"]`);
    expect(src).toContain(`hint: "${ARTIFACTS_COMMAND_HINT}"`);
  });

  it("builds the same paths the web panel builds", () => {
    const src = readFileSync(
      resolve(
        repoRoot(),
        "packages/ui/src/components/chat/stock/artifacts-panel.tsx",
      ),
      "utf8",
    );
    expect(src).toContain("/api/conversations/${encodeURIComponent(conversationId)}/artifacts");
    expect(src).toContain("${artifactListPath(conversationId)}/blob?token=${encodeURIComponent(token)}");

    expect(artifactListUrl(BASE, "a/b c")).toBe(
      `${BASE}/api/conversations/a%2Fb%20c/artifacts`,
    );
    expect(artifactBlobUrl(BASE, CONVERSATION, "tok/1")).toBe(
      `${BASE}/api/conversations/${CONVERSATION}/artifacts/blob?token=tok%2F1`,
    );
    expect(conversationCreateUrl(BASE)).toBe(`${BASE}/api/conversations`);
  });
});

describe("row cursor (nextArtifactIndex)", () => {
  it("wraps past the last row and past the first row", () => {
    expect(nextArtifactIndex(0, 1, 3)).toBe(1);
    expect(nextArtifactIndex(2, 1, 3)).toBe(0);
    expect(nextArtifactIndex(0, -1, 3)).toBe(2);
  });

  it("stays put for a single row and reports nothing selectable when empty", () => {
    expect(nextArtifactIndex(0, 1, 1)).toBe(0);
    expect(nextArtifactIndex(0, -1, 1)).toBe(0);
    expect(nextArtifactIndex(0, 1, 0)).toBe(-1);
  });
});
