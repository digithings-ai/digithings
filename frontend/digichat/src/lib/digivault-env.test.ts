import { describe, it, expect, afterEach } from "vitest";
import { resolveDigivaultEnv, DigivaultEnvError } from "./digivault-env";

afterEach(() => {
  delete process.env.CORE_SUPABASE_URL;
  delete process.env.CORE_SUPABASE_ANON_KEY;
  delete process.env.OPENROUTER_API_KEY;
});

describe("resolveDigivaultEnv", () => {
  it("resolves env names to values", () => {
    process.env.CORE_SUPABASE_URL = "https://example.supabase.co";
    process.env.CORE_SUPABASE_ANON_KEY = "anon";
    process.env.OPENROUTER_API_KEY = "sk-or-v1-x";
    expect(
      resolveDigivaultEnv({
        type: "digivault",
        supabaseUrlEnv: "CORE_SUPABASE_URL",
        supabaseAnonKeyEnv: "CORE_SUPABASE_ANON_KEY",
        openRouterKeyEnv: "OPENROUTER_API_KEY",
      })
    ).toEqual({
      supabaseUrl: "https://example.supabase.co",
      supabaseAnonKey: "anon",
      openRouterKey: "sk-or-v1-x",
    });
  });

  it("fails closed without echoing values", () => {
    process.env.CORE_SUPABASE_URL = "https://example.supabase.co";
    try {
      resolveDigivaultEnv({
        type: "digivault",
        supabaseUrlEnv: "CORE_SUPABASE_URL",
        supabaseAnonKeyEnv: "CORE_SUPABASE_ANON_KEY",
        openRouterKeyEnv: "OPENROUTER_API_KEY",
      });
      expect.unreachable();
    } catch (e) {
      expect(e).toBeInstanceOf(DigivaultEnvError);
      const msg = String(e);
      expect(msg).not.toContain("https://example.supabase.co");
      expect(msg).toMatch(/not configured|missing/i);
    }
  });
});
