import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import {
  assertDevAuthDisabledInProduction,
  isDevAuthEnabled,
  isProductionLike,
} from "./startup-env-guards";

/** Every value a deployed `.env` can plausibly put in DIGICHAT_DEV_AUTH. */
const DEV_AUTH_VALUES = [
  undefined,
  "",
  " ",
  "0",
  "false",
  "no",
  "2",
  "1",
  " 1 ",
  "1\r",
];

const NON_PRODUCTION_ENVS = [
  undefined,
  "",
  "development",
  "test",
  "dev",
];

/**
 * NODE_ENV spellings that mean production without being the exact
 * string `production` — the historical silent bypass. Next.js sets
 * `production` itself, but operators and orchestrators routinely
 * pass `prod` or a case variant.
 */
const PRODUCTION_LIKE_ENVS = [
  "production",
  "prod",
  "PRODUCTION",
  "Production",
  "PROD",
  "Prod",
  " production ",
];

describe("isDevAuthEnabled", () => {
  it("is on only for a trimmed 1", () => {
    const on = DEV_AUTH_VALUES.filter((v) => isDevAuthEnabled({ DIGICHAT_DEV_AUTH: v }));
    expect(on).toEqual(["1", " 1 ", "1\r"]);
  });
});

describe("assertDevAuthDisabledInProduction", () => {
  // ProcessEnv types NODE_ENV as readonly; the guard reads it at runtime like
  // any other variable, so drive it through a mutable view.
  const env = process.env as unknown as Record<string, string | undefined>;

  afterEach(() => {
    delete env.NODE_ENV;
    delete env.DIGICHAT_DEV_AUTH;
  });

  it("throws in production when the dev flag is 1", () => {
    expect(() => assertDevAuthDisabledInProduction({ NODE_ENV: "production", DIGICHAT_DEV_AUTH: "1" })).toThrow(
      /digichat refused to start/,
    );
  });

  it("names both variables in the failure", () => {
    let message = "";
    try {
      assertDevAuthDisabledInProduction({ NODE_ENV: "production", DIGICHAT_DEV_AUTH: "1" });
    } catch (e) {
      message = e instanceof Error ? e.message : String(e);
    }
    expect(message).toContain("NODE_ENV");
    expect(message).toContain("DIGICHAT_DEV_AUTH");
    // The companion credential is what an operator has to remove alongside the flag.
    expect(message).toContain("DIGICHAT_DEV_PASSWORD");
  });

  it("throws for the CRLF spelling a Windows .env produces", () => {
    expect(() =>
      assertDevAuthDisabledInProduction({ NODE_ENV: "production", DIGICHAT_DEV_AUTH: "1\r" }),
    ).toThrow(/digichat refused to start/);
  });

  it("throws for prod-like NODE_ENV spellings, not only the exact string", () => {
    // Previously silent bypass: NODE_ENV=prod (or a case variant of
    // production) slipped past the `!== "production"` check.
    for (const nodeEnv of PRODUCTION_LIKE_ENVS) {
      expect(() =>
        assertDevAuthDisabledInProduction({ NODE_ENV: nodeEnv, DIGICHAT_DEV_AUTH: "1" }),
      ).toThrow(/digichat refused to start/);
    }
  });

  it("names the NODE_ENV spelling it refused", () => {
    let message = "";
    try {
      assertDevAuthDisabledInProduction({ NODE_ENV: "prod", DIGICHAT_DEV_AUTH: "1" });
    } catch (e) {
      message = e instanceof Error ? e.message : String(e);
    }
    expect(message).toContain('"prod"');
  });

  it("throws in production with the flag set through the real process env", () => {
    env.NODE_ENV = "production";
    env.DIGICHAT_DEV_AUTH = "1";
    expect(() => assertDevAuthDisabledInProduction()).toThrow(/NODE_ENV/);
  });

  it("stays silent in production whenever the flag is not enabled", () => {
    for (const value of DEV_AUTH_VALUES) {
      if (isDevAuthEnabled({ DIGICHAT_DEV_AUTH: value })) continue;
      expect(() =>
        assertDevAuthDisabledInProduction({ NODE_ENV: "production", DIGICHAT_DEV_AUTH: value }),
      ).not.toThrow();
    }
    expect(() => assertDevAuthDisabledInProduction({ NODE_ENV: "production" })).not.toThrow();
  });

  it("stays silent outside production, flag or not", () => {
    for (const nodeEnv of NON_PRODUCTION_ENVS) {
      for (const value of DEV_AUTH_VALUES) {
        expect(() =>
          assertDevAuthDisabledInProduction({ NODE_ENV: nodeEnv, DIGICHAT_DEV_AUTH: value }),
        ).not.toThrow();
      }
    }
  });

  /**
   * The security invariant behind the guard: in a production-like
   * environment there must be no value where the provider is enabled
   * but the assertion stays quiet — and no non-production environment
   * where it throws.
   */
  it("throws for exactly the production-like environments that enable the provider", () => {
    for (const nodeEnv of [...PRODUCTION_LIKE_ENVS, ...NON_PRODUCTION_ENVS]) {
      for (const value of DEV_AUTH_VALUES) {
        const env = { NODE_ENV: nodeEnv, DIGICHAT_DEV_AUTH: value };
        let threw = false;
        try {
          assertDevAuthDisabledInProduction(env);
        } catch {
          threw = true;
        }
        expect(threw).toBe(isProductionLike(nodeEnv) && isDevAuthEnabled(env));
      }
    }
  });
});

/**
 * `@/auth` calls NextAuth at module scope and is not importable outside a Next
 * build (`next/server` does not resolve), so the two call sites are pinned by
 * reading them. Without this the guard could pass every test above while sitting
 * un-called in the source — which is exactly how the gap opened.
 */
describe("guard call sites", () => {
  const read = (rel: string) =>
    readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

  it("runs before anything else at startup", () => {
    const instrumentation = read("../instrumentation.ts");
    expect(instrumentation).toContain("assertDevAuthDisabledInProduction()");
    const guardIndex = instrumentation.indexOf("assertDevAuthDisabledInProduction()");
    // Ahead of every other initializer, so the mistake is diagnosed before any
    // database, license or migration work begins.
    for (const later of ["initDigichatConfigAtStartup", "initLicenseStateAtStartup", "runMigrate"]) {
      expect(guardIndex).toBeLessThan(instrumentation.indexOf(later));
    }
  });

  it("guards the dev provider before it can be registered", () => {
    const auth = read("../auth.ts");
    const guardIndex = auth.indexOf("assertDevAuthDisabledInProduction()");
    expect(guardIndex).toBeGreaterThan(-1);
    expect(guardIndex).toBeLessThan(auth.indexOf("const dev = devProvider()"));
  });
});
