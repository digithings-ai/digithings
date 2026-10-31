/**
 * Tenant chrome config (client-repos epic, Phase 2 U5a). One block per Guard
 * rule, plus the legacy fallback and the `models.allowPicker` alias. Example
 * tenants only (`example`, `example-b`); no live model calls.
 */
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  HOUSE_ROUTE_SEGMENTS,
  classifyTenantChatPath,
  pathsOverlap,
  gatedTenantClaims,
  lastGoodGatedClaimCountForTests,
  rememberGatedTenantDocs,
  resetGatedTenantCacheForTests,
  resolveTenantChatSlug,
  tenantChatPath,
  tenantChatSlugFromPath,
  validateTenantChatSlug,
} from "./tenant-chrome";
import { DeploymentSchema, DigichatConfigSchema, productChat } from "./schema";
import { loadDigichatConfig, matchHostDeployment, resetDigichatConfigForTests } from "./loader";
import {
  getEmbedTenantRegistry,
  parseEmbedTenants,
  resetEmbedTenantRegistryForTests,
} from "@/lib/embed-tenants";
import { toEmbedClientConfig } from "@/lib/embed-client-config";
import { getTenantSuggestionPool } from "@/lib/embed-suggestion-pools";
import { inviteRequiredButMissing, isInviteOnlyDeployment } from "@/lib/embed-invite-only";
import { GET as tenantConfigGET } from "@/app/api/embed/tenant-config/route";

const HOST_A = "chat.example.com";
const HOST_B = "chat.example-b.com";
const INVITE_REF = "EXAMPLE_INVITE_KEY_REF";
const TOKEN_A = "example-embed-token-fixture";

function row(overrides: Record<string, unknown> = {}) {
  return {
    slug: "example",
    backend: { type: "digigraph" },
    gateMode: "ungated",
    theme: "light",
    attribution: true,
    token: TOKEN_A,
    ...overrides,
  };
}

/** A product chat row needs a TPM (or an explicit `guardrails.tpmLimit: false`). */
const TPM = { tokensPerMinute: { user: 80_000 } };

function registry(rows: Record<string, unknown>) {
  return JSON.stringify(rows);
}

function hostDeployment(host: string, tenants: Record<string, unknown>) {
  const config = loadDigichatConfig({ env: { DIGICHAT_EMBED_TENANTS: registry(tenants) } });
  const dep = matchHostDeployment(host, config);
  if (!dep) throw new Error(`no deployment for ${host}`);
  return dep;
}

beforeEach(() => {
  resetGatedTenantCacheForTests();
  resetEmbedTenantRegistryForTests();
  resetDigichatConfigForTests();
});

afterEach(() => {
  vi.unstubAllEnvs();
  resetGatedTenantCacheForTests();
  resetEmbedTenantRegistryForTests();
  resetDigichatConfigForTests();
});

describe("chrome.slug: R0 builds /chat/<slug>", () => {
  it("builds the path and reads the slug back from it", () => {
    expect(tenantChatPath("example")).toBe("/chat/example");
    expect(tenantChatSlugFromPath("/chat/example")).toBe("example");
    expect(tenantChatSlugFromPath("/chat/example-b/thread/1")).toBe("example-b");
    expect(tenantChatSlugFromPath("/chat")).toBeNull();
    expect(tenantChatSlugFromPath("/chat/api/chat")).toBeNull();
    expect(tenantChatSlugFromPath("/embed")).toBeNull();
  });

  it("validates a plain slug and returns it with the path", () => {
    expect(validateTenantChatSlug("example")).toEqual({
      ok: true,
      slug: "example",
      path: "/chat/example",
    });
    expect(validateTenantChatSlug("example-b").ok).toBe(true);
  });
});

describe("Guard: the slug is a plain lowercase slug", () => {
  it.each(["Example", "example_b", "-example", "example-", "example--b", "", "/chat/example", "ex ample", "exämple", "%65xample", ".."])(
    "refuses %j",
    (value) => {
      const result = validateTenantChatSlug(value);
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.reason).toBe("not-a-slug");
    },
  );
});

describe("Guard: no overlap with house routes", () => {
  it.each(["chat", "api", "embed", "dashboard", "devkit", "tools", "healthz", "baseline"])(
    "refuses the house segment %j",
    (value) => {
      const result = validateTenantChatSlug(value);
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.reason).toBe("house-route");
    },
  );

  it("reserves every top-level route of the app (route groups stripped)", () => {
    const appDir = join(__dirname, "../../app");
    const segments = new Set<string>();
    const hasRoute = (dir: string): boolean =>
      readdirSync(dir).some((name) => {
        const full = join(dir, name);
        if (statSync(full).isDirectory()) return hasRoute(full);
        return /^(page|route)\.(t|j)sx?$/.test(name) || name.endsWith(".ts");
      });
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const full = join(dir, name);
        if (!statSync(full).isDirectory()) continue;
        if (name.startsWith("(") && name.endsWith(")")) walk(full);
        else if (hasRoute(full)) segments.add(name);
      }
    };
    walk(appDir);
    expect(segments.size).toBeGreaterThan(3);
    for (const segment of segments) expect(HOUSE_ROUTE_SEGMENTS.has(segment)).toBe(true);
  });

  it("the schema refuses a house segment in chrome.slug", () => {
    const parsed = DeploymentSchema.safeParse({
      slug: "example",
      backend: { type: "digigraph" },
      chrome: { slug: "api" },
    });
    expect(parsed.success).toBe(false);
  });
});

describe("Guard: no collision with another tenant", () => {
  it("compares whole path segments", () => {
    expect(pathsOverlap("/chat/abc", "/chat/abcd")).toBe(false);
    expect(pathsOverlap("/chat", "/chat/x")).toBe(true);
    expect(pathsOverlap("/chat/example", "/chat/example")).toBe(true);
  });

  it("refuses a slug another tenant uses, allows rows of one tenant to share it", () => {
    const others = [{ tenant: "example", chatSlug: "example" }];
    const clash = validateTenantChatSlug("example", { tenant: "example-b", others });
    expect(clash.ok).toBe(false);
    if (!clash.ok) expect(clash.reason).toBe("collision");
    expect(validateTenantChatSlug("example", { tenant: "example", others }).ok).toBe(true);
    expect(validateTenantChatSlug("example-b", { tenant: "example-b", others }).ok).toBe(true);
  });

  it("the config schema refuses two tenants on one slug", () => {
    const doc = (slug: string) => ({
      slug,
      backend: { type: "digigraph" },
      chrome: { slug: "example" },
    });
    expect(
      DigichatConfigSchema.safeParse({
        version: 1,
        hosts: { [HOST_A]: doc("example"), [HOST_B]: doc("example-b") },
      }).success,
    ).toBe(false);
    expect(
      DigichatConfigSchema.safeParse({
        version: 1,
        hosts: { [HOST_A]: doc("example"), "www.chat.example.com": doc("example") },
      }).success,
    ).toBe(true);
  });

  it("the registry refuses two tenants on one slug", () => {
    expect(() =>
      parseEmbedTenants(
        registry({
          [HOST_A]: row({ chatSlug: "example" }),
          [HOST_B]: row({ slug: "example-b", chatSlug: "example" }),
        }),
      ),
    ).toThrow(/already used/);
  });
});

describe("TODO(P-exit) legacy stored chrome.pathPrefix", () => {
  it("validates /chat/<slug>, folds it onto the slug, and builds the same path byte for byte", () => {
    const stored = "/chat/example";
    const parsed = DeploymentSchema.parse({
      slug: "example",
      backend: { type: "digigraph" },
      chrome: { pathPrefix: stored },
    });
    expect(parsed.chrome.slug).toBe("example");
    expect("pathPrefix" in parsed.chrome).toBe(false);
    expect(tenantChatPath(parsed.chrome.slug as string)).toBe(stored);
  });

  it("agrees with the slug when both are set, and is refused when they disagree", () => {
    expect(resolveTenantChatSlug({ slug: "example", pathPrefix: "/chat/example" })).toEqual({
      ok: true,
      slug: "example",
    });
    expect(resolveTenantChatSlug({ slug: "example", pathPrefix: "/chat/example-b" }).ok).toBe(
      false,
    );
    expect(
      DeploymentSchema.safeParse({
        slug: "example",
        backend: { type: "digigraph" },
        chrome: { slug: "example", pathPrefix: "/chat/example-b" },
      }).success,
    ).toBe(false);
    expect(() =>
      parseEmbedTenants(registry({ [HOST_A]: row({ chatSlug: "example", pathPrefix: "/chat/example-b" }) })),
    ).toThrow(/disagree/);
  });

  it.each(["/chat", "/chat/", "/chat/example/", "/chat/example/x", "/api/example", "/chat/Example", "chat/example", "/chat/api"])(
    "refuses the legacy shape %j",
    (pathPrefix) => {
      expect(resolveTenantChatSlug({ pathPrefix }).ok).toBe(false);
    },
  );

  it("a legacy registry pathPrefix matches the gated claims check", () => {
    vi.stubEnv(
      "DIGICHAT_EMBED_TENANTS",
      registry({ [HOST_A]: row({ gateMode: "invite", pathPrefix: "/chat/example" }) }),
    );
    const cfg = getEmbedTenantRegistry().get(HOST_A);
    expect(cfg?.chatSlug).toBe("example");
    // The registry is now unreadable: the last-good claim still gates the path.
    expect(classifyTenantChatPath("/chat/example", null)).toEqual({
      kind: "gated-unknown",
      chatSlug: "example",
    });
  });
});

describe("Guard: the client config is an allowlist (access.invite never leaks)", () => {
  const tenants = {
    [HOST_A]: row({
      title: "Example chat",
      chatSlug: "example",
      productChat: true,
      guardrails: TPM,
      gateMode: "invite",
      access: {
        invite: { cookieName: "example_invite", label: "Example invite", keyRef: INVITE_REF },
      },
      models: {
        available: ["model-a"],
        default: "model-a",
        allowPicker: true,
        occPicker: true,
        priceCapUsdPerMillion: 3,
        costPerWindow: { usd: 1, windowSeconds: 3600 },
      },
      mcp: {
        servers: [
          { id: "docs", url: "https://mcp.example.com", tokenEnv: "EXAMPLE_MCP_TOKEN" },
        ],
      },
    }),
    [HOST_B]: row({ slug: "example-b", title: "Example B chat", token: "example-b-token" }),
  };

  it("parses access.invite server-side", () => {
    const cfg = parseEmbedTenants(registry(tenants)).get(HOST_A);
    expect(cfg?.access?.invite?.cookieName).toBe("example_invite");
  });

  it("toEmbedClientConfig carries no access, token, tokenEnv or server model policy", () => {
    const cfg = parseEmbedTenants(registry(tenants)).get(HOST_A);
    if (!cfg) throw new Error("no tenant");
    const projected = toEmbedClientConfig(cfg);
    expect("access" in projected).toBe(false);
    const json = JSON.stringify(projected);
    for (const secret of [INVITE_REF, "example_invite", TOKEN_A, "EXAMPLE_MCP_TOKEN", "tokenEnv", "costPerWindow", "occPicker", "priceCapUsdPerMillion", "mcp.example.com"]) {
      expect(json).not.toContain(secret);
    }
    expect(projected.models).toEqual({ default: "model-a", available: ["model-a"], allowPicker: true });
  });

  it("an access block added later with unknown keys still never reaches the client", () => {
    const cfg = parseEmbedTenants(
      registry({ [HOST_A]: row({ access: { invite: { futureSecretField: "future-secret-value" } } }) }),
    ).get(HOST_A);
    if (!cfg) throw new Error("no tenant");
    expect(JSON.stringify(toEmbedClientConfig(cfg))).not.toContain("future-secret-value");
  });

  it("GET /api/embed/tenant-config answers only the requested tenant's display fields", async () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", registry(tenants));
    const res = await tenantConfigGET(
      new Request("http://127.0.0.1/api/embed/tenant-config", {
        headers: { "x-embed-host": `https://${HOST_A}`, "x-embed-token": TOKEN_A },
      }),
    );
    expect(res.status).toBe(200);
    const text = await res.text();
    const body = JSON.parse(text);
    expect(body.slug).toBe("example");
    expect(body.title).toBe("Example chat");
    expect("access" in body).toBe(false);
    expect("token" in body).toBe(false);
    for (const leak of [INVITE_REF, TOKEN_A, "example-b-token", "Example B chat", "EXAMPLE_MCP_TOKEN"]) {
      expect(text).not.toContain(leak);
    }
  });
});

describe("Guard: gated tenants fail closed (claims live outside the doc)", () => {
  it("a /chat/<slug> path with no valid doc is never the house default", () => {
    expect(classifyTenantChatPath("/chat/example", null)).toEqual({
      kind: "gated-unknown",
      chatSlug: "example",
    });
    expect(classifyTenantChatPath("/chat/example", [])).toEqual({
      kind: "gated-unknown",
      chatSlug: "example",
    });
    expect(classifyTenantChatPath("/chat", null)).toEqual({ kind: "house" });
    expect(classifyTenantChatPath("/chat/api/chat", null)).toEqual({ kind: "house" });
    expect(
      classifyTenantChatPath("/chat/example", [{ slug: "example", chatSlug: "example", gated: false }]),
    ).toEqual({ kind: "tenant", slug: "example", gated: false });
  });

  it("a claimed path stays gated when its doc goes missing, and even if a doc says ungated", () => {
    rememberGatedTenantDocs([{ slug: "example", chatSlug: "example", host: HOST_A, gated: true }]);
    expect(classifyTenantChatPath("/chat/example", null).kind).toBe("gated-unknown");
    expect(
      classifyTenantChatPath("/chat/example", [{ slug: "example", chatSlug: "example", gated: false }]),
    ).toEqual({ kind: "tenant", slug: "example", gated: true });
  });

  it("missing, unreadable and invalid registries keep a claimed host denied", async () => {
    // Last good registry: example is gated.
    vi.stubEnv(
      "DIGICHAT_EMBED_TENANTS",
      registry({ [HOST_A]: row({ chatSlug: "example", gateMode: "invite" }) }),
    );
    expect(inviteRequiredButMissing(HOST_A, "embed")).toBe(true);
    expect(inviteRequiredButMissing(HOST_A, "example")).toBe(false);

    for (const broken of ["{not json", "", registry({ [HOST_A]: row({ chatSlug: "API!" }) })]) {
      vi.stubEnv("DIGICHAT_EMBED_TENANTS", broken);
      resetEmbedTenantRegistryForTests();
      resetDigichatConfigForTests();
      expect(isInviteOnlyDeployment(HOST_A, null)).toBe(true);
      expect(inviteRequiredButMissing(HOST_A, "embed")).toBe(true);
      const res = await tenantConfigGET(
        new Request("http://127.0.0.1/api/embed/tenant-config", {
          headers: { "x-embed-host": `https://${HOST_A}` },
        }),
      );
      expect(res.status).toBe(404);
      const text = await res.text();
      expect(text).not.toContain("example");
    }
  });

  it("an invite-gated registry row without its token is denied", async () => {
    vi.stubEnv(
      "DIGICHAT_EMBED_TENANTS",
      registry({ [HOST_B]: row({ slug: "example-b", access: { invite: { cookieName: "b_invite" } } }) }),
    );
    const res = await tenantConfigGET(
      new Request("http://127.0.0.1/api/embed/tenant-config", {
        headers: { "x-embed-host": `https://${HOST_B}` },
      }),
    );
    expect(res.status).toBe(404);
  });
});

describe("chrome.productChat and the models.allowPicker alias", () => {
  const picker = (models: Record<string, unknown>) =>
    hostDeployment(HOST_A, {
      [HOST_A]: row({
        productChat: true,
        guardrails: TPM,
        models: { available: ["model-a"], default: "model-a", ...models },
      }),
    });

  it("productChat comes from the tenant doc, not the host", () => {
    const dep = hostDeployment(HOST_A, { [HOST_A]: row({ productChat: true, guardrails: TPM }) });
    expect(dep.chrome.productChat).toBe(true);
    expect(productChat(HOST_A, dep)).toBe("tenant");
    const plain = hostDeployment(HOST_A, { [HOST_A]: row() });
    expect(productChat(HOST_A, plain)).toBeNull();
  });

  it("allowPicker false locks the picker to the operator model", () => {
    const dep = picker({ allowPicker: false });
    expect(dep.features.modelPicker).toBe(false);
    expect(dep.models.available).toEqual([]);
  });

  it("legacy occPicker is accepted as the allowPicker alias, both ways", () => {
    const effective = (dep: ReturnType<typeof picker>) => ({
      modelPicker: dep.features.modelPicker,
      available: dep.models.available,
      default: dep.models.default,
      allowPicker: dep.models.allowPicker,
      picker: dep.models.picker,
    });
    expect(effective(picker({ occPicker: false }))).toEqual(effective(picker({ allowPicker: false })));
    const viaAlias = picker({ occPicker: true });
    const viaField = picker({ allowPicker: true });
    expect(viaAlias.features.modelPicker).toBe(viaField.features.modelPicker);
    expect(viaAlias.models.available).toEqual(viaField.models.available);
    expect(viaAlias.models.default).toEqual(viaField.models.default);
  });

  it("allowPicker wins over the alias when both are set", () => {
    const dep = picker({ allowPicker: true, occPicker: false });
    expect(dep.models.available).toEqual(["model-a"]);
  });

});

describe("chrome.productChat: safe by default, explicit opt-outs", () => {
  const limited = (extra: Record<string, unknown> = {}, models: Record<string, unknown> = {}) =>
    hostDeployment(HOST_A, {
      [HOST_A]: row({
        productChat: true,
        guardrails: { tokensPerMinute: { deployment: 100_000, user: 80_000 } },
        models: {
          available: ["model-a"],
          default: "model-a",
          priceCapUsdPerMillion: 3,
          costPerWindow: { usd: 1, windowSeconds: 60 },
          ...models,
        },
        ...extra,
      }),
    });

  it("pins the default for a new productChat row: meter on, TPM on, picker off", () => {
    const dep = limited();
    expect(productChat(HOST_A, dep)).toBe("tenant");
    expect(dep.models.costPerWindow).toEqual({ usd: 1, windowSeconds: 60 });
    expect(dep.guardrails?.tokensPerMinute).toEqual({ deployment: 100_000, user: 80_000 });
    expect(dep.features.modelPicker).toBe(false);
    expect(dep.models.allowPicker).toBe(false);
    expect(dep.models.picker).toBeUndefined();
    expect(dep.models.catalog).toBeUndefined();
    // The row's own list stays the allowlist.
    expect(dep.models.available).toEqual(["model-a"]);
  });

  it("a bare productChat row gets no catalog picker", () => {
    const dep = hostDeployment(HOST_A, { [HOST_A]: row({ productChat: true, guardrails: TPM }) });
    expect(dep.features.modelPicker).toBe(false);
    expect(dep.models.allowPicker).toBe(false);
    expect(dep.models.catalog).toBeUndefined();
    expect(dep.models.picker).toBeUndefined();
  });

  it("the opt-outs work: allowPicker, premiumMeter: false, guardrails.tpmLimit: false", () => {
    const meterOff = limited({}, { premiumMeter: false });
    expect(meterOff.models.costPerWindow).toBeUndefined();
    expect(meterOff.guardrails?.tokensPerMinute).toEqual({ deployment: 100_000, user: 80_000 });

    const tpmOff = limited({
      guardrails: { tpmLimit: false, tokensPerMinute: { deployment: 100_000, user: 80_000 } },
    });
    expect(tpmOff.guardrails?.tokensPerMinute).toBeUndefined();
    expect(tpmOff.models.costPerWindow).toEqual({ usd: 1, windowSeconds: 60 });

    const pickerOn = limited({}, { allowPicker: true });
    expect(pickerOn.features.modelPicker).toBe(true);
    expect(pickerOn.models.costPerWindow).toEqual({ usd: 1, windowSeconds: 60 });

    const aliasOn = limited({}, { occPicker: true });
    expect(aliasOn.features.modelPicker).toBe(true);

    const allOff = limited(
      { guardrails: { tpmLimit: false, tokensPerMinute: { deployment: 100_000, user: 80_000 } } },
      { allowPicker: true, premiumMeter: false },
    );
    expect(allOff.features.modelPicker).toBe(true);
    expect(allOff.models.costPerWindow).toBeUndefined();
    expect(allOff.guardrails?.tokensPerMinute).toBeUndefined();
  });

  it("an opened catalog picker with no written window gets the house meter", () => {
    const dep = hostDeployment(HOST_A, {
      [HOST_A]: row({ productChat: true, guardrails: TPM, models: { allowPicker: true } }),
    });
    expect(dep.features.modelPicker).toBe(true);
    expect(dep.models.catalog).toBe(true);
    expect(dep.models.costPerWindow?.usd).toBeGreaterThan(0);
    const optedOut = hostDeployment(HOST_A, {
      [HOST_A]: row({
        productChat: true,
        guardrails: TPM,
        models: { allowPicker: true, premiumMeter: false },
      }),
    });
    expect(optedOut.models.costPerWindow).toBeUndefined();
  });

  it("the registry refuses a non-boolean premiumMeter", () => {
    expect(() =>
      parseEmbedTenants(registry({ [HOST_A]: row({ models: { premiumMeter: "no" } }) })),
    ).toThrow(/premiumMeter must be a boolean/);
  });
});

describe("chrome.productChat: TPM on with no number is refused", () => {
  const productRow = (guardrails?: Record<string, unknown>) =>
    row({ productChat: true, chatSlug: "example", ...(guardrails ? { guardrails } : {}) });
  const deploymentDoc = (guardrails?: Record<string, unknown>) => ({
    slug: "example",
    chrome: { productChat: true },
    backend: { type: "digigraph" },
    ...(guardrails ? { guardrails } : {}),
  });

  it("a new productChat row with no tokensPerMinute is refused by the schema check", () => {
    for (const g of [undefined, {}, { tpmLimit: true }, { tokensPerMinute: {} }]) {
      const res = DeploymentSchema.safeParse(deploymentDoc(g));
      expect(res.success).toBe(false);
      if (!res.success) {
        expect(res.error.issues.map((i) => i.message).join("\n")).toMatch(
          /chrome\.productChat needs a positive guardrails\.tokensPerMinute/,
        );
      }
    }
  });

  it("the registry loader refuses the same row, and the tenant fails closed", async () => {
    expect(() => parseEmbedTenants(registry({ [HOST_A]: productRow() }))).toThrow(
      /chrome\.productChat needs a positive guardrails\.tokensPerMinute/,
    );
    expect(() =>
      loadDigichatConfig({ env: { DIGICHAT_EMBED_TENANTS: registry({ [HOST_A]: productRow() }) } }),
    ).toThrow(/tokensPerMinute/);

    vi.stubEnv("DIGICHAT_EMBED_TENANTS", registry({ [HOST_A]: productRow() }));
    expect(() => getEmbedTenantRegistry()).toThrow(/tokensPerMinute/);
    // No valid doc: the tenant path is gated-unknown, never the house default.
    expect(classifyTenantChatPath("/chat/example", null)).toEqual({
      kind: "gated-unknown",
      chatSlug: "example",
    });
    const res = await tenantConfigGET(
      new Request("http://127.0.0.1/api/embed/tenant-config", {
        headers: { "x-embed-host": `https://${HOST_A}` },
      }),
    );
    expect(res.status).toBe(404);
    expect(await res.text()).not.toContain("example");
  });

  it("the same row with guardrails.tpmLimit: false loads", () => {
    expect(DeploymentSchema.safeParse(deploymentDoc({ tpmLimit: false })).success).toBe(true);
    const dep = hostDeployment(HOST_A, { [HOST_A]: productRow({ tpmLimit: false }) });
    expect(productChat(HOST_A, dep)).toBe("tenant");
    expect(dep.guardrails?.tokensPerMinute).toBeUndefined();
  });

  it("the same row with a positive tokensPerMinute loads and keeps that number", () => {
    expect(
      DeploymentSchema.safeParse(deploymentDoc({ tokensPerMinute: { deployment: 120_000 } })).success,
    ).toBe(true);
    const dep = hostDeployment(HOST_A, {
      [HOST_A]: productRow({ tokensPerMinute: { deployment: 120_000, user: 40_000 } }),
    });
    expect(dep.guardrails?.tokensPerMinute).toEqual({ deployment: 120_000, user: 40_000 });
  });

  it("a zero, negative or non-numeric tokensPerMinute is refused", () => {
    for (const bad of [0, -1, "80000", Number.NaN, 1.5]) {
      const g = { tokensPerMinute: { user: bad } };
      expect(DeploymentSchema.safeParse(deploymentDoc(g)).success).toBe(false);
      expect(() => parseEmbedTenants(registry({ [HOST_A]: productRow(g) }))).toThrow();
    }
  });

  it("a row that is not a product chat needs no TPM", () => {
    expect(() => parseEmbedTenants(registry({ [HOST_A]: row() }))).not.toThrow();
  });
});

describe("Guard: the last-good gated claims are deduped on write", () => {
  it("loading the same registry N times leaves the claim count unchanged", () => {
    const gated = { [HOST_A]: row({ gateMode: "invite", chatSlug: "example" }) };
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", registry(gated));
    getEmbedTenantRegistry();
    const once = lastGoodGatedClaimCountForTests();
    const claims = gatedTenantClaims().length;
    expect(once).toBe(1);
    for (let i = 0; i < 25; i += 1) {
      resetEmbedTenantRegistryForTests();
      getEmbedTenantRegistry();
    }
    expect(lastGoodGatedClaimCountForTests()).toBe(once);
    expect(gatedTenantClaims().length).toBe(claims);
    expect(inviteRequiredButMissing(HOST_A, "other")).toBe(true);
  });

  it("the shared claims list is frozen at runtime; a caller cannot change it", () => {
    rememberGatedTenantDocs([{ slug: "example", chatSlug: "example", host: HOST_A, gated: true }]);
    const claims = gatedTenantClaims();
    const before = JSON.stringify(claims);
    expect(Object.isFrozen(claims)).toBe(true);
    for (const claim of claims) expect(Object.isFrozen(claim)).toBe(true);
    const mine = claims.find((c) => c.host === HOST_A);
    if (!mine) throw new Error("no claim");
    // ES modules run in strict mode: writes to a frozen object throw.
    expect(() => (claims as unknown as Array<unknown>).push({ slug: "x", chatSlug: "x" })).toThrow(TypeError);
    expect(() => (claims as unknown as Array<unknown>).pop()).toThrow(TypeError);
    expect(() => {
      (mine as { host?: string }).host = "attacker.example.net";
    }).toThrow(TypeError);
    expect(() => {
      (mine as { chatSlug: string }).chatSlug = "other";
    }).toThrow(TypeError);
    expect(JSON.stringify(gatedTenantClaims())).toBe(before);
    expect(gatedTenantClaims()).toBe(claims);
    expect(inviteRequiredButMissing(HOST_A, "other")).toBe(true);
    expect(classifyTenantChatPath("/chat/example", null).kind).toBe("gated-unknown");
  });

  it("the caller's own doc objects are not frozen by remembering them", () => {
    const doc = { slug: "example", chatSlug: "example", host: HOST_A, gated: true };
    rememberGatedTenantDocs([doc]);
    expect(Object.isFrozen(doc)).toBe(false);
  });

  it("direct repeated writes of the same claim store it once", () => {
    const doc = { slug: "example", chatSlug: "example", host: HOST_A, gated: true };
    for (let i = 0; i < 10; i += 1) rememberGatedTenantDocs([doc, doc]);
    expect(lastGoodGatedClaimCountForTests()).toBe(1);
  });
});

describe("chrome.suggestions come from the tenant doc", () => {
  it("code keeps no pool for an example tenant; the doc's pool is projected", () => {
    expect(getTenantSuggestionPool("example")).toBeUndefined();
    const cfg = parseEmbedTenants(registry({ [HOST_A]: row({ suggestions: ["Ask me"] }) })).get(HOST_A);
    if (!cfg) throw new Error("no tenant");
    expect(toEmbedClientConfig(cfg).suggestions).toEqual(["Ask me"]);
  });
});
