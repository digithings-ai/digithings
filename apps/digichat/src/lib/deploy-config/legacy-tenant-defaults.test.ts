/**
 * TODO(P-exit): the legacy fallback for the live gated tenant. Every value is
 * read from the constants (here and in the Worker gate), never retyped, so
 * this file names no tenant. Delete with legacy-tenant-defaults.ts.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  LEGACY_INVITE_EMBED_HOST as WORKER_GATED_HOST,
  LEGACY_INVITE_PAGE_PATH as WORKER_GATED_PATH,
} from "../../../../digichat-cloudflare/src/legacy-invite-gate";
import {
  LEGACY_GATED_TENANTS,
  LEGACY_GATED_TENANT_HOST,
  LEGACY_GATED_TENANT_PRODUCT_CHAT,
  LEGACY_GATED_TENANT_SLUG,
} from "./legacy-tenant-defaults";
import {
  classifyTenantChatPath,
  resetGatedTenantCacheForTests,
  resolveTenantChatSlug,
  tenantChatPath,
} from "./tenant-chrome";
import { loadDigichatConfig, matchHostDeployment } from "./loader";
import { productChat } from "./schema";
import { INVITE_ONLY_EMBED_HOSTS, inviteRequiredButMissing } from "@/lib/embed-invite-only";
import { resetEmbedTenantRegistryForTests } from "@/lib/embed-tenants";
import {
  OCC_SUGGESTION_POOL as LEGACY_POOL,
  getTenantSuggestionPool,
} from "@/lib/embed-suggestion-pools";

beforeEach(() => {
  resetGatedTenantCacheForTests();
  resetEmbedTenantRegistryForTests();
});
afterEach(() => {
  resetGatedTenantCacheForTests();
  resetEmbedTenantRegistryForTests();
});

/** The live row's shape (no new fields), keyed by the legacy host. */
function legacyRow(extra: Record<string, unknown> = {}) {
  return {
    slug: LEGACY_GATED_TENANT_SLUG,
    backend: { type: "digigraph" },
    gateMode: "ungated",
    layout: "page",
    theme: "light",
    attribution: true,
    token: "legacy-token-fixture",
    models: { occPicker: true },
    ...extra,
  };
}

function legacyDeployment(row: Record<string, unknown>) {
  const config = loadDigichatConfig({
    env: { DIGICHAT_EMBED_TENANTS: JSON.stringify({ [LEGACY_GATED_TENANT_HOST]: row }) },
  });
  const dep = matchHostDeployment(LEGACY_GATED_TENANT_HOST, config);
  if (!dep) throw new Error("no legacy deployment");
  return dep;
}

describe("legacy gated tenant: one source with the Worker gate", () => {
  it("the R0 path and host equal the Worker's byte for byte", () => {
    expect(LEGACY_GATED_TENANT_HOST).toBe(WORKER_GATED_HOST);
    expect(tenantChatPath(LEGACY_GATED_TENANT_SLUG)).toBe(WORKER_GATED_PATH);
  });

  it("the Worker's stored full path normalises to the slug and builds the same path", () => {
    const resolved = resolveTenantChatSlug({ pathPrefix: WORKER_GATED_PATH });
    expect(resolved).toEqual({ ok: true, slug: LEGACY_GATED_TENANT_SLUG });
    if (resolved.ok) expect(tenantChatPath(resolved.slug as string)).toBe(WORKER_GATED_PATH);
  });

  it("is claimed outside the doc: denied with no doc, the host stays invite-only", () => {
    expect(LEGACY_GATED_TENANTS).toHaveLength(1);
    expect(classifyTenantChatPath(WORKER_GATED_PATH, null)).toEqual({
      kind: "gated-unknown",
      chatSlug: LEGACY_GATED_TENANT_SLUG,
    });
    expect(INVITE_ONLY_EMBED_HOSTS.get(WORKER_GATED_HOST)).toBe(LEGACY_GATED_TENANT_SLUG);
    expect(inviteRequiredButMissing(WORKER_GATED_HOST, "embed")).toBe(true);
    expect(inviteRequiredButMissing(WORKER_GATED_HOST, LEGACY_GATED_TENANT_SLUG)).toBe(false);
  });
});

describe("legacy fallback equivalence", () => {
  it("the live row without new fields is still the tenant product chat", () => {
    expect(productChat(LEGACY_GATED_TENANT_HOST, legacyDeployment(legacyRow()))).toBe("tenant");
  });

  it("the same row with the new fields resolves to the same deployment", () => {
    const legacy = legacyDeployment(legacyRow());
    const migrated = legacyDeployment(
      legacyRow({
        chatSlug: LEGACY_GATED_TENANT_SLUG,
        productChat: true,
        suggestions: [...LEGACY_POOL],
        // The explicit opt-outs that replace LEGACY_GATED_TENANT_PRODUCT_CHAT.
        guardrails: { tpmLimit: false },
        models: { allowPicker: true, premiumMeter: false },
      }),
    );
    const strip = (dep: typeof legacy) => {
      const chrome = { ...dep.chrome };
      delete chrome.slug;
      delete chrome.productChat;
      delete chrome.suggestions;
      const models = { ...dep.models };
      delete models.occPicker;
      delete models.premiumMeter;
      const guardrails = dep.guardrails ? { ...dep.guardrails } : undefined;
      if (guardrails) delete guardrails.tpmLimit;
      const rest = { ...dep, chrome, models };
      delete (rest as { guardrails?: unknown }).guardrails;
      return { ...rest, guardrailsOut: guardrails && Object.keys(guardrails).length ? guardrails : undefined };
    };
    expect(strip(migrated)).toEqual(strip(legacy));
  });

  it("the picker lock keeps its legacy rule on the legacy row", () => {
    const locked = legacyDeployment(legacyRow({ models: { occPicker: false } }));
    expect(locked.features.modelPicker).toBe(false);
    expect(locked.models.available).toEqual([]);
    const open = legacyDeployment(legacyRow());
    expect(open.features.modelPicker).toBe(true);
  });

  it("pins the legacy row's current behaviour: no meter, no TPM, picker on", () => {
    expect(LEGACY_GATED_TENANT_PRODUCT_CHAT).toEqual({
      premiumMeter: false,
      tpmLimit: false,
      picker: true,
    });
    const dep = legacyDeployment(
      legacyRow({
        guardrails: { tokensPerMinute: { deployment: 100_000, user: 80_000 } },
        models: {
          occPicker: true,
          priceCapUsdPerMillion: 3,
          costPerWindow: { usd: 1, windowSeconds: 60 },
        },
      }),
    );
    expect(dep.features.modelPicker).toBe(true);
    expect(dep.models.allowPicker).toBe(true);
    expect(dep.models.catalog).toBe(true);
    expect(dep.models.costPerWindow).toBeUndefined();
    expect(dep.guardrails?.tokensPerMinute).toBeUndefined();
    const bare = legacyDeployment(legacyRow({ models: {} }));
    expect(bare.features.modelPicker).toBe(true);
    expect(bare.models.costPerWindow).toBeUndefined();
  });

  it("a row without suggestions keeps the legacy pool", () => {
    expect(getTenantSuggestionPool(LEGACY_GATED_TENANT_SLUG)).toEqual([...LEGACY_POOL]);
  });
});
