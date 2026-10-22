// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToolCatalogBar } from "./tool-catalog-bar";
import { DEFAULT_CLIENT_CONFIG } from "@/lib/deploy-config";
import { takePendingForceTool } from "@/lib/pending-chat-headers";

function stubMapStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => {
      store.set(k, v);
    },
    removeItem: (k: string) => {
      store.delete(k);
    },
    clear: () => store.clear(),
  });
}

const catalogConfig = {
  ...DEFAULT_CLIENT_CONFIG,
  tools: {
    allowUserToggle: true,
    catalog: [
      { id: "digisearch", default: true, label: "Search" },
      { id: "digivault", default: true, label: "Vault" },
      { id: "web_search", default: false, label: "Web search" },
    ],
  },
  gate: { ...DEFAULT_CLIENT_CONFIG.gate, webSearch: true },
};

describe("ToolCatalogBar", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not render web or force chips", () => {
    stubMapStorage();
    takePendingForceTool("host-a");
    render(
      <ToolCatalogBar
        clientConfig={{ ...catalogConfig, slug: "occ" }}
        sessionKey="host-a"
        webSearchScope="web-scope"
        onWebSearchChange={vi.fn()}
      />,
    );
    expect(document.querySelector("[data-tool-catalog]")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    expect(takePendingForceTool("host-a")).toBeUndefined();
  });

  it("renders nothing for an empty catalog and for a locked catalog", () => {
    const { rerender } = render(
      <ToolCatalogBar
        clientConfig={{
          ...DEFAULT_CLIENT_CONFIG,
          tools: { allowUserToggle: true, catalog: [] },
        }}
        sessionKey="host-a"
      />,
    );
    expect(document.querySelector("[data-tool-catalog]")).toBeNull();
    rerender(
      <ToolCatalogBar
        clientConfig={{
          ...catalogConfig,
          tools: { ...catalogConfig.tools, allowUserToggle: false },
        }}
        sessionKey="host-a"
      />,
    );
    expect(document.querySelector("[data-tool-catalog]")).toBeNull();
  });

  it("defaults the web toggle on for baseline and matched tenants (#3859)", () => {
    // House client fallback, no stored pref: default-on.
    stubMapStorage();
    const { unmount } = render(
      <ToolCatalogBar
        clientConfig={catalogConfig}
        sessionKey="baseline-scope"
        webSearchScope="baseline-web-default"
      />,
    );
    expect(catalogConfig.slug).toBe("digithings-ai");
    expect(screen.getByRole("button", { name: "Web search" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    unmount();
    // Matched tenant slug with no stored pref: also default-on now.
    stubMapStorage();
    const { unmount: unmountTenant } = render(
      <ToolCatalogBar
        clientConfig={{ ...catalogConfig, slug: "occ" }}
        sessionKey="tenant-scope"
        webSearchScope="tenant-web-default"
      />,
    );
    expect(screen.getByRole("button", { name: "Web search" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    unmountTenant();
  });

  it("renders no web toggle for deny tenants (gate off, no web_search entry)", () => {
    // datatap shape: gate.webSearch false and no web_search catalog entry —
    // the tenant AND-gate denies, so no toggle renders and nothing sends.
    stubMapStorage();
    // Trial shape: gate.webSearch false and no web_search catalog entry.
    const denyConfig = {
      ...catalogConfig,
      slug: "datatap",
      tools: {
        allowUserToggle: true,
        catalog: [
          { id: "digisearch", default: true, label: "Search" },
          { id: "digivault", default: true, label: "Vault" },
        ],
      },
      gate: { ...DEFAULT_CLIENT_CONFIG.gate, webSearch: false },
    };
    render(
      <ToolCatalogBar
        clientConfig={denyConfig}
        sessionKey="deny-scope"
        webSearchScope="deny-web-default"
      />,
    );
    expect(screen.queryByRole("button", { name: "Web search" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Search" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Vault" })).toBeNull();
  });
});
