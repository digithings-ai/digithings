import { describe, it, expect, vi, afterEach } from "vitest";
import { searchArchitectureNotes, buildToolContext } from "./digivault-vault";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("digivault-vault", () => {
  it("projects activity documents without body_markdown", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            vault_path: "arch/digikey.md",
            title: "DigiKey",
            body_markdown: "# secret body",
          },
        ]),
        { status: 200 },
      ),
    );
    const hits = await searchArchitectureNotes({
      supabaseUrl: "https://example.supabase.co",
      supabaseAnonKey: "anon",
      query: "digikey",
    });
    const { toolText, activityDocuments } = buildToolContext(hits);
    expect(toolText).toContain("secret body");
    expect(JSON.stringify(activityDocuments)).not.toContain("secret body");
    expect(JSON.stringify(activityDocuments)).not.toContain("body_markdown");
    expect(activityDocuments[0]).toEqual({ title: "DigiKey", path: "arch/digikey.md" });
  });

  it("posts CF-parity RPC body field names", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    );
    await searchArchitectureNotes({
      supabaseUrl: "https://example.supabase.co/",
      supabaseAnonKey: "anon",
      query: "ports",
      matchCount: 4,
    });
    expect(fetchSpy).toHaveBeenCalledWith(
      "https://example.supabase.co/rest/v1/rpc/search_architecture_notes",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ query: "ports", match_limit: 4 }),
      }),
    );
  });
});
