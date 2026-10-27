import { describe, expect, it } from "vitest";
import { dataPlaneEnv, type Env } from "./env";

/** Names that may be forwarded empty: the execution-probe mail path reads
 * them as optional, so an unset binding must still arrive. */
const MAIL_NAMES = [
  "CLOUDFLARE_ACCOUNT_ID",
  "CLOUDFLARE_EMAIL_API_TOKEN",
  "NOTIFY_FROM",
];

/** The full forwarded-name allowlist. */
const FORWARDED_NAMES = [
  "CHEAPERINFERENCE_API_BASE",
  "CHEAPERINFERENCE_API_KEY",
  "CLOUDFLARE_ACCOUNT_ID",
  "CLOUDFLARE_EMAIL_API_TOKEN",
  "CORE_POSTGRES_URI",
  "CORE_SUPABASE_SERVICE_KEY",
  "CORE_SUPABASE_URL",
  "DIGIQUANT_DIGIKEY_API_KEY",
  "DIGIQUANT_RUNNER_GIT_SHA",
  "DIGI_OTEL_HEADERS",
  "NOTIFY_FROM",
  "OPENROUTER_API_KEY",
  "R2_ACCESS_KEY_ID",
  "R2_ACCOUNT_ID",
  "R2_BUCKET",
  "R2_SECRET_ACCESS_KEY",
];

function envWith(values: Record<string, string>): Env {
  return { ...values, RUNNER_CONTAINER: {} as DurableObjectNamespace };
}

describe("dataPlaneEnv", () => {
  it("omits an unset optional variable instead of forwarding an empty string", () => {
    const forwarded = dataPlaneEnv(envWith({}));
    expect(forwarded).not.toHaveProperty("CHEAPERINFERENCE_API_BASE");
    expect(forwarded).not.toHaveProperty("DIGIQUANT_RUNNER_GIT_SHA");
    expect(forwarded).not.toHaveProperty("LANGSMITH_API_KEY");
    expect(Object.keys(forwarded)).not.toContain("LANGSMITH_API_KEY");
  });

  it("leaves only the mail names in the forwarded env when nothing is set", () => {
    const forwarded = dataPlaneEnv(envWith({}));
    expect(Object.keys(forwarded).sort()).toEqual([...MAIL_NAMES].sort());
    for (const name of MAIL_NAMES) expect(forwarded[name]).toBe("");
  });

  it("forwards a set value verbatim", () => {
    const forwarded = dataPlaneEnv(
      envWith({
        CHEAPERINFERENCE_API_BASE: "https://example.invalid/v1",
        R2_BUCKET: "a-bucket",
      }),
    );
    expect(forwarded.CHEAPERINFERENCE_API_BASE).toBe(
      "https://example.invalid/v1",
    );
    expect(forwarded.R2_BUCKET).toBe("a-bucket");
  });

  it("never forwards an empty value for a name outside the mail allowlist", () => {
    const forwarded = dataPlaneEnv(
      envWith({
        CHEAPERINFERENCE_API_BASE: "",
        CORE_SUPABASE_URL: "",
        NOTIFY_FROM: "",
      }),
    );
    expect(forwarded).not.toHaveProperty("CHEAPERINFERENCE_API_BASE");
    expect(forwarded).not.toHaveProperty("CORE_SUPABASE_URL");
    // The mail name is still forwarded, empty.
    expect(forwarded.NOTIFY_FROM).toBe("");
  });

  it("keeps the forwarded-name allowlist unchanged when every name is set", () => {
    const values: Record<string, string> = {};
    for (const name of FORWARDED_NAMES) values[name] = `value-${name}`;
    const forwarded = dataPlaneEnv(envWith(values));
    expect(Object.keys(forwarded).sort()).toEqual([...FORWARDED_NAMES].sort());
    for (const name of FORWARDED_NAMES) {
      expect(forwarded[name]).toBe(`value-${name}`);
    }
  });

  it("does not forward the runner auth token, the issue token or a FRED key", () => {
    const forwarded = dataPlaneEnv(
      envWith({
        RUNNER_AUTH_TOKEN: "nope",
        GH_ISSUE_TOKEN: "nope",
        FRED_API_KEY: "nope",
      }),
    );
    expect(forwarded).not.toHaveProperty("RUNNER_AUTH_TOKEN");
    expect(forwarded).not.toHaveProperty("GH_ISSUE_TOKEN");
    expect(forwarded).not.toHaveProperty("FRED_API_KEY");
  });
});
