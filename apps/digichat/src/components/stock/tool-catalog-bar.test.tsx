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

  // The web-toggle assertions that used to live here are gone with the toggle:
  // #6211 moved tool toggles into /tools, and the first test in this file
  // already pins the rule that the bar renders no chips at all. The /tools
  // behaviour is covered by embed-composer-menu.*.test.tsx.
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
