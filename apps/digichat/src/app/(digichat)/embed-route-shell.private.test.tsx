/**
 * First paint of a private embed page (Bugbot on #6623, Medium).
 *
 * A `?private=1` page for a tenant that opted in to private mode must not carry
 * the tenant's own copy in its initial HTML: not in the server-rendered markup,
 * and not in the props the server hands the client component (the RSC payload
 * Next serialises into the same document). Normal mode keeps the tenant copy.
 *
 * Neutral fixture only: "Fixturedesk" is a made-up help desk.
 */
import { createElement, isValidElement, type ReactElement } from "react";
import { prerender } from "react-dom/static";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetEmbedTenantRegistryForTests } from "@/lib/embed-tenants";
import { resetDigichatConfigForTests } from "@/lib/deploy-config/loader";
import {
  PRIVATE_HEADER_TITLE,
  PRIVATE_PLACEHOLDER,
  PRIVATE_SUGGESTIONS,
  PRIVATE_WELCOME,
} from "@/lib/private-chrome";

let requestHeaders = new Headers();
vi.mock("next/headers", () => ({ headers: async () => requestHeaders }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
  useRouter: () => ({ push() {}, replace() {}, refresh() {}, back() {}, prefetch() {} }),
  usePathname: () => "/embed",
  useSearchParams: () => new URLSearchParams(),
}));

const { default: EmbedRouteShell } = await import("./embed-route-shell");

const HOST = "help.fixturedesk.test";
const TOKEN = "fixture-embed-token-not-real";
const TENANT_TITLE = "Fixturedesk help assistant";
const TENANT_WELCOME = "Ask about Fixturedesk policies, procedures, and help articles.";
const TENANT_PLACEHOLDER = "Ask Fixturedesk anything";
const TENANT_SUGGESTIONS = [
  "How does Fixturedesk route a new ticket?",
  "Where is the Fixturedesk escalation policy?",
  "Show the Fixturedesk onboarding checklist",
];
/** Every tenant string, plus the tenant name on its own (catches any copy that names it). */
const TENANT_STRINGS = [TENANT_TITLE, TENANT_WELCOME, TENANT_PLACEHOLDER, ...TENANT_SUGGESTIONS, "Fixturedesk"];

function registry(privateMode: boolean | undefined): string {
  return JSON.stringify({
    [HOST]: {
      slug: "fixture",
      gateMode: "ungated",
      layout: "page",
      llmAccess: "free_then_byok",
      attribution: false,
      title: TENANT_TITLE,
      welcome: TENANT_WELCOME,
      placeholder: TENANT_PLACEHOLDER,
      suggestions: TENANT_SUGGESTIONS,
      token: TOKEN,
      backend: { type: "digigraph", digisearchIndex: "fixture_help", vaultPathPrefix: "clients/fixture" },
      ...(privateMode === undefined ? {} : { privateMode }),
    },
  });
}

/** The props of the client component the shell renders: what the RSC payload serialises. */
function clientProps(node: unknown): Record<string, unknown>[] {
  const found: Record<string, unknown>[] = [];
  const walk = (n: unknown) => {
    if (Array.isArray(n)) return n.forEach(walk);
    if (!isValidElement(n)) return;
    const el = n as ReactElement<Record<string, unknown>>;
    const props = el.props ?? {};
    if (typeof el.type === "function" && "initialTenantCfg" in props) found.push(props);
    walk(props.children);
  };
  walk(node);
  return found;
}

async function renderShell(params: Record<string, string>) {
  const tree = await EmbedRouteShell({ params: { host: HOST, ...params } });
  const props = clientProps(tree);
  expect(props).toHaveLength(1);
  // Wait for every Suspense boundary (the thread skin is lazy), as Next does
  // for the streamed document, so the welcome and chips are in the markup.
  const { prelude } = await prerender(createElement(() => tree));
  const html = await new Response(prelude).text();
  expect(html).not.toContain("Switched to client rendering");
  return { html, props: JSON.stringify(props) };
}

beforeEach(() => {
  vi.stubEnv("DIGICHAT_EMBED_TENANTS", registry(true));
  vi.stubEnv("DIGICHAT_CONFIG_PATH", "");
  requestHeaders = new Headers({ "x-embed-token": TOKEN });
  resetEmbedTenantRegistryForTests();
  resetDigichatConfigForTests();
});

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
  resetDigichatConfigForTests();
});

describe("embed first paint in a private session", () => {
  it("normal mode keeps the tenant's own copy (fixture sanity)", async () => {
    const { html, props } = await renderShell({});
    expect(html).toContain(TENANT_WELCOME);
    expect(props).toContain(TENANT_TITLE);
    expect(props).toContain(TENANT_WELCOME);
    expect(props).toContain(TENANT_PLACEHOLDER);
    for (const s of TENANT_SUGGESTIONS) expect(props).toContain(s);
    expect(html).not.toContain(PRIVATE_WELCOME);
  });

  it("?private=1 for an opted-in tenant: no tenant string in the HTML or the client props", async () => {
    const { html, props } = await renderShell({ private: "1" });
    for (const s of TENANT_STRINGS) {
      expect(html, `HTML carries "${s}"`).not.toContain(s);
      expect(props, `client props carry "${s}"`).not.toContain(s);
    }
    expect(html).toContain(PRIVATE_WELCOME);
    expect(props).toContain(PRIVATE_PLACEHOLDER);
    expect(props).toContain(JSON.stringify(PRIVATE_HEADER_TITLE));
    for (const s of PRIVATE_SUGGESTIONS) expect(props).toContain(s);
  });

  it("a tenant that did not opt in ignores ?private=1 and keeps its copy", async () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", registry(undefined));
    resetEmbedTenantRegistryForTests();
    const { html, props } = await renderShell({ private: "1" });
    expect(html).toContain(TENANT_WELCOME);
    expect(props).toContain(TENANT_TITLE);
    expect(html).not.toContain(PRIVATE_WELCOME);
  });

  it("only an exact ?private=1 masks the first paint", async () => {
    for (const value of ["0", "true", ""]) {
      const { props } = await renderShell({ private: value });
      expect(props, `?private=${value}`).toContain(TENANT_WELCOME);
    }
  });
});
