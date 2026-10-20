import { afterEach, describe, expect, it, vi } from "vitest";
import { supaGet } from "./supabase";
import { tableRows } from "./table-read";

const seen: Array<{ url: string; headers: Record<string, string> }> = [];

function mockFetch(out: unknown): void {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: { headers?: Record<string, string> }) => {
    seen.push({ url, headers: init?.headers ?? {} });
    return Response.json(out, { status: 200 });
  }));
}

afterEach(() => {
  seen.length = 0;
  vi.unstubAllGlobals();
});

const LEGACY = "eyJhbGciOiJIUzI1NiJ9.legacy.service.role.token";
const NEW_SECRET = "sb_secret_fde_read_path_probe";
const NEW_PUBLISHABLE = "sb_publishable_fde_read_path_probe";

describe("supaGet header shape", () => {
  it("keeps apikey and Authorization for a legacy key", async () => {
    mockFetch([]);
    await supaGet({ SUPABASE_URL: "https://core.supabase.co", SUPABASE_SERVICE_ROLE_KEY: LEGACY }, "t");
    expect(seen).toHaveLength(1);
    expect(seen[0].headers.apikey).toBe(LEGACY);
    expect(seen[0].headers.Authorization).toBe(`Bearer ${LEGACY}`);
  });

  it("sends a new-format secret key on apikey only", async () => {
    mockFetch([]);
    await supaGet({ SUPABASE_URL: "https://tx.supabase.co", SUPABASE_SERVICE_ROLE_KEY: NEW_SECRET }, "t");
    expect(seen).toHaveLength(1);
    expect(seen[0].headers.apikey).toBe(NEW_SECRET);
    expect(Object.keys(seen[0].headers)).not.toContain("Authorization");
  });

  it("sends a new-format publishable key on apikey only", async () => {
    mockFetch([]);
    await supaGet({ SUPABASE_URL: "https://tx.supabase.co", SUPABASE_SERVICE_ROLE_KEY: NEW_PUBLISHABLE }, "t");
    expect(seen[0].headers.apikey).toBe(NEW_PUBLISHABLE);
    expect(Object.keys(seen[0].headers)).not.toContain("Authorization");
  });
});

describe("twelve-x read path with a new-format key", () => {
  it("reads the twelve-x project with apikey only", async () => {
    mockFetch([{ date: "2026-10-19" }]);
    const res = await tableRows(
      {
        SUPABASE_URL: "https://core.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY: LEGACY,
        TWELVEX_SUPABASE_URL: "https://tx.supabase.co",
        TWELVEX_SUPABASE_SERVICE_KEY: NEW_SECRET,
      },
      { table: "fx_rates", project: "twelvex" },
    );
    expect("rows" in res).toBe(true);
    expect(seen).toHaveLength(1);
    expect(seen[0].url).toContain("https://tx.supabase.co/rest/v1/fx_rates");
    expect(seen[0].headers.apikey).toBe(NEW_SECRET);
    expect(Object.keys(seen[0].headers)).not.toContain("Authorization");
  });
});
