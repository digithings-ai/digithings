/**
 * Slice 1 of the one-config epic (docs/plans/digichat-one-config-epic.md).
 *
 * The two tenant documents must resolve to the SAME effective deployment as
 * today's live config sources:
 *
 *   config/digithings.yaml  ≡  KV `config-yaml` + KV `embed-tenants`
 *   config/occ.yaml         ≡  the same, at occ.digithings.ai
 *
 * The expectation is built, never hand-copied: the live KV values are pinned
 * here (the OCC tenant entry verbatim, the house document in
 * `__fixtures__/live-kv-config-yaml.yaml`) and run through the code the Worker
 * and container run today — `mergeTenants` (tokenEnv → token, exactly what the
 * Worker does before handing the container DIGICHAT_EMBED_TENANTS), then
 * `loadDigichatConfig` (expandExtends → parseEmbedTenants → the host merge →
 * applyCatalogConfig). A failure reads as "a document drifted from live", so
 * re-read the KV key rather than editing the assertion.
 *
 * Nothing reads either document in production yet; this test is the whole
 * acceptance bar for slice 1.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { mergeTenants } from "../../../../digichat-cloudflare/src/tenants-kv";
import { INVITE_ONLY_EMBED_HOSTS } from "@/lib/embed-invite-only";
import type { DigichatDeployment } from "./schema";
import { loadDigichatConfig, matchHostDeployment } from "./loader";

const CONFIG_DIR = new URL("../../../config/", import.meta.url);
const FIXTURES_DIR = new URL("./__fixtures__/", import.meta.url);

const houseDocumentText = () => readFileSync(new URL("digithings.yaml", CONFIG_DIR), "utf8");
const occDocumentText = () => readFileSync(new URL("occ.yaml", CONFIG_DIR), "utf8");
const liveHouseDocumentText = () =>
  readFileSync(new URL("live-kv-config-yaml.yaml", FIXTURES_DIR), "utf8");

const OCC_HOST = "occ.digithings.ai";
const HOUSE_HOST = "digithings.ai";

/**
 * The secrets the live KV entry references. Fixture values, never real keys —
 * the same shape `apps/digichat-cloudflare/src/tenants-kv.test.ts` uses.
 */
const SECRETS: Record<string, string> = {
  OCC_INVITE_KEY: "occ-invite-key-fixture-not-a-secret",
  ZAMMAD_EDGE_KEY: "zammad-edge-key-fixture-not-a-secret",
};

/**
 * KV `embed-tenants`, verbatim as read from the `DIGICHAT_TENANTS_KV`
 * namespace (26 Oct 2026; tokenEnv refs only, no values). Pinned so a live
 * edit to the tenant row fails this test instead of drifting silently.
 */
const EMBED_TENANTS_KV = `
{
  "occ.digithings.ai": {
    "activityDetail": "full",
    "attribution": true,
    "backend": {
      "digisearchIndex": "occ_help,occ-tickets",
      "type": "digigraph",
      "vaultPathPrefix": "clients/online-compliance-center"
    },
    "gateMode": "ungated",
    "layout": "page",
    "llmAccess": "free_then_byok",
    "lockSessionControls": true,
    "mcp": {
      "servers": [
        {
          "allowedTools": [
            "search_tickets",
            "list_tickets",
            "get_ticket",
            "ticket_report",
            "aggregate_tickets"
          ],
          "authHeader": "x-digi-mcp-key",
          "default": true,
          "id": "zammad",
          "mutatingTools": [],
          "tokenEnv": "ZAMMAD_EDGE_KEY",
          "url": "https://digithings.ai/api/mcp/zammad/mcp"
        },
        {
          "authScheme": "jwt",
          "default": true,
          "id": "digisearch",
          "setup": { "index_name": "occ_help" },
          "url": "https://search.digithings.ai/_stack/mcp/digisearch/mcp"
        },
        {
          "authScheme": "jwt",
          "default": true,
          "id": "digivault",
          "setup": { "path_prefix": "clients/online-compliance-center" },
          "url": "https://graph.digithings.ai/_stack/mcp/digivault/mcp"
        }
      ]
    },
    "models": { "occPicker": true },
    "showByok": true,
    "showStatusBar": true,
    "slug": "occ",
    "title": "OCC help assistant",
    "tokenEnv": "OCC_INVITE_KEY",
    "tools": {
      "catalog": [
        {
          "default": true,
          "id": "digisearch",
          "label": "digisearch",
          "tools": [{ "id": "digisearch" }, { "id": "digisearch_zammad_tickets" }]
        },
        {
          "default": true,
          "id": "digivault",
          "label": "digivault",
          "tools": [
            { "id": "digivault_search_notes" },
            { "id": "digivault_get_note" },
            { "id": "digivault_search_tag" },
            { "id": "digivault_backlinks" }
          ]
        }
      ]
    },
    "webSearch": false,
    "welcome": "Ask about Online Compliance Center policies, procedures, and help articles."
  }
}
`;

/** Today's resolution: the Worker's tenant merge, then the container loader. */
function todaysConfig() {
  const tenants = mergeTenants(EMBED_TENANTS_KV, undefined, SECRETS);
  expect(tenants.unresolved).toEqual({});
  return loadDigichatConfig({
    fileContents: liveHouseDocumentText(),
    env: { DIGICHAT_EMBED_TENANTS: tenants.json, ...SECRETS },
  });
}

/** A document from `apps/digichat/config/`, through the same real loader. */
function configFromDocument(text: string) {
  return loadDigichatConfig({ fileContents: text, env: { ...SECRETS } });
}

function hostDeployment(
  host: string,
  config: ReturnType<typeof loadDigichatConfig>,
): DigichatDeployment {
  const dep = matchHostDeployment(host, config);
  if (!dep) throw new Error(`no hosts.${host} deployment resolved`);
  return dep;
}

/**
 * What the equivalence assertion compares on an MCP server: everything the
 * operator set. Credentials are compared separately, because the two paths
 * carry them differently — the Worker has already turned a `tokenEnv` ref into
 * a value by the time the container sees the tenant row, while a document
 * carries the ref and the loader resolves it. `mcpTokens` and `mcpTokenEnvs`
 * below assert that both end at the same secret.
 */
function mcpShape(dep: DigichatDeployment) {
  return (dep.mcp?.servers ?? []).map((server) => ({
    id: server.id,
    url: server.url,
    label: server.label ?? null,
    default: server.default ?? false,
    authScheme: server.authScheme ?? null,
    authHeader: server.authHeader ?? null,
    setup: server.setup ?? {},
    allowedTools: server.allowedTools ?? [],
    mutatingTools: server.mutatingTools ?? [],
  }));
}

function mcpTokens(dep: DigichatDeployment) {
  return (dep.mcp?.servers ?? []).map((server) => server.token ?? null);
}

function mcpTokenEnvs(dep: DigichatDeployment) {
  return (dep.mcp?.servers ?? []).map((server) => server.tokenEnv ?? null);
}

describe("digithings.ai — config/digithings.yaml equals today's house resolution", () => {
  const expected = hostDeployment(HOUSE_HOST, todaysConfig());
  const actual = hostDeployment(HOUSE_HOST, configFromDocument(houseDocumentText()));

  it("resolves the house slug", () => {
    expect(actual.slug).toBe(expected.slug);
    expect(actual.slug).toBe("digithings-ai");
  });

  it("resolves identical chrome", () => {
    expect(actual.chrome).toEqual(expected.chrome);
    expect(actual.chrome.mode).toBe("app");
    expect(actual.chrome.theme).toBe("dark");
    expect(actual.chrome.skin).toBe("digichat");
  });

  it("resolves identical models (catalog included)", () => {
    expect(actual.models).toEqual(expected.models);
    expect(actual.models.catalog).toBe(true);
  });

  it("resolves identical tools", () => {
    expect(actual.tools).toEqual(expected.tools);
  });

  it("resolves identical MCP servers, url for url", () => {
    expect(mcpShape(actual)).toEqual(mcpShape(expected));
    expect(mcpShape(actual).map((s) => s.url)).toEqual([
      "https://search.digithings.ai/_stack/mcp/digisearch/mcp",
      "https://graph.digithings.ai/_stack/mcp/digivault/mcp",
    ]);
  });

  it("resolves identical gate, including the house meter and web search", () => {
    expect(actual.gate).toEqual(expected.gate);
    expect(actual.gate.mode).toBe("ungated");
  });

  it("resolves the same embed token ref", () => {
    expect(actual.tokenEnv).toBe(expected.tokenEnv);
    expect(actual.tokenEnv).toBe("DIGICHAT_HOST_DIGITHINGS_AI_TOKEN");
  });
});

describe("occ.digithings.ai — config/occ.yaml equals today's live tenant", () => {
  const expected = hostDeployment(OCC_HOST, todaysConfig());
  const actual = hostDeployment(OCC_HOST, configFromDocument(occDocumentText()));

  /**
   * Today's OCC gate is enforced at the EDGE (embed-invite-only.ts, mirrored by
   * the Worker's occ-gate.ts), not in the tenant row — the KV row still says
   * `ungated`. The document has to say what is actually enforced, so the
   * expected mode is derived from the invite-host map, not from the row.
   */
  const edgeGateMode = INVITE_ONLY_EMBED_HOSTS.has(OCC_HOST) ? "invite" : expected.gate.mode;

  it("resolves the OCC slug", () => {
    expect(actual.slug).toBe(expected.slug);
    expect(actual.slug).toBe("occ");
  });

  it("resolves the page layout as chrome.mode app", () => {
    // The tenant row says `layout: page`; `embedTenantToDeployment` maps
    // page → app, and ChromeModeSchema has no "page".
    expect(actual.chrome.mode).toBe(expected.chrome.mode);
    expect(actual.chrome.mode).toBe("app");
  });

  it("keeps the carried chrome fields", () => {
    expect(actual.chrome.skin).toBe(expected.chrome.skin);
    expect(actual.chrome.title).toBe(expected.chrome.title);
    expect(actual.chrome.title).toBe("OCC help assistant");
    expect(actual.chrome.welcome).toEqual(expected.chrome.welcome);
    expect(actual.chrome.attribution).toBe(expected.chrome.attribution);
  });

  it("declares the light theme the surface actually paints", () => {
    // The ONE field a document states differently from live: the KV row omits
    // `theme`, so the parser default is `dark`. Asserted explicitly so the
    // delta cannot hide behind the fields compared below.
    expect(expected.chrome.theme).toBe("dark");
    expect(actual.chrome.theme).toBe("light");
  });

  it("resolves the invite gate mode the edge enforces", () => {
    expect(actual.gate.mode).toBe(edgeGateMode);
    expect(actual.gate.mode).toBe("invite");
  });

  it("keeps every gate field the tenant row carries", () => {
    expect(actual.gate.activityDetail).toBe(expected.gate.activityDetail);
    expect(actual.gate.activityDetail).toBe("full");
    expect(actual.gate.llmAccess).toBe(expected.gate.llmAccess);
    expect(actual.gate.llmAccess).toBe("free_then_byok");
    expect(actual.gate.showByok).toBe(expected.gate.showByok);
    expect(actual.gate.showByok).toBe(true);
    expect(actual.gate.lockSessionControls).toBe(expected.gate.lockSessionControls);
    expect(actual.gate.lockSessionControls).toBe(true);
    expect(actual.gate.webSearch).toBe(expected.gate.webSearch);
    expect(actual.gate.webSearch).toBe(false);
  });

  it("resolves the OCC backend index and vault prefix", () => {
    expect(actual.backend).toEqual(expected.backend);
    expect(actual.backend).toMatchObject({
      type: "digigraph",
      digisearchIndex: "occ_help,occ-tickets",
      vaultPathPrefix: "clients/online-compliance-center",
    });
  });

  it("resolves the same models policy (picker on, no premium meter)", () => {
    expect(actual.models).toEqual(expected.models);
    expect(actual.models.occPicker).toBe(true);
    expect(actual.models.costPerWindow).toBeUndefined();
  });

  it("resolves the same tool catalog", () => {
    expect(actual.tools).toEqual(expected.tools);
  });

  it("resolves the same MCP servers: id, url, auth, setup, allowlist", () => {
    expect(mcpShape(actual)).toEqual(mcpShape(expected));
    expect(mcpShape(actual)).toEqual([
      {
        id: "zammad",
        url: "https://digithings.ai/api/mcp/zammad/mcp",
        label: null,
        default: true,
        authScheme: null,
        authHeader: "x-digi-mcp-key",
        setup: {},
        allowedTools: [
          "search_tickets",
          "list_tickets",
          "get_ticket",
          "ticket_report",
          "aggregate_tickets",
        ],
        mutatingTools: [],
      },
      {
        id: "digisearch",
        url: "https://search.digithings.ai/_stack/mcp/digisearch/mcp",
        label: null,
        default: true,
        authScheme: "jwt",
        authHeader: null,
        setup: { index_name: "occ_help" },
        allowedTools: [],
        mutatingTools: [],
      },
      {
        id: "digivault",
        url: "https://graph.digithings.ai/_stack/mcp/digivault/mcp",
        label: null,
        default: true,
        authScheme: "jwt",
        authHeader: null,
        setup: { path_prefix: "clients/online-compliance-center" },
        allowedTools: [],
        mutatingTools: [],
      },
    ]);
  });

  it("resolves the same MCP credentials from the same env refs", () => {
    // The document names the refs; today's path carries the resolved values.
    expect(mcpTokenEnvs(actual)).toEqual(["ZAMMAD_EDGE_KEY", null, null]);
    expect(mcpTokenEnvs(expected)).toEqual([null, null, null]);
    expect(mcpTokens(actual)).toEqual(mcpTokens(expected));
    expect(mcpTokens(actual)).toEqual([SECRETS.ZAMMAD_EDGE_KEY, null, null]);
  });

  it("resolves the invite key from its env ref, never a value", () => {
    expect(actual.tokenEnv).toBe("OCC_INVITE_KEY");
    expect(actual.token).toBe(expected.token);
    expect(actual.token).toBe(SECRETS.OCC_INVITE_KEY);
  });

  it("keeps the non-inherited attachments default", () => {
    // The tenant row carries no features block; the legacy bridge resolves
    // attachments to false (explicit-true-only). The document states it.
    expect(actual.features.attachments).toBe(expected.features.attachments);
    expect(actual.features.attachments).toBe(false);
  });
});

describe("both documents are full documents, not overlays", () => {
  const documents: Array<[name: string, read: () => string, host: string]> = [
    ["digithings.yaml", houseDocumentText, HOUSE_HOST],
    ["occ.yaml", occDocumentText, OCC_HOST],
  ];

  it.each(documents)(
    "%s carries no `extends` and resolves from its own hosts map",
    (_name, read, host) => {
      const text = read();
      expect(text).not.toMatch(/^extends:/m);
      // No DIGICHAT_EMBED_TENANTS in the env: the document is complete on its
      // own, with no overlay to make it valid.
      expect(configFromDocument(text).hosts).toBeDefined();
      expect(Object.keys(configFromDocument(text).hosts ?? {})).toEqual([host]);
    },
  );
});
