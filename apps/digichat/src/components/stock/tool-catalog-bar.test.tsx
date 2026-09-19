// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToolCatalogBar } from "./tool-catalog-bar";
import { DEFAULT_CLIENT_CONFIG } from "@/lib/deploy-config";
import { takePendingForceTool } from "@/lib/pending-chat-headers";

function stubMapStorage() {
  // happy-dom ships a non-functional localStorage — stub a real Map so the
  // effect sync reads the missing-key default, not the catch branch.
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
  it("arms X-Digi-Force-Tool on Search / Vault and isolates web search prefs", async () => {
    // Matched-tenant slug: the toggle starts on (#3859 default-on) so this
    // test exercises the interaction from the on state. Stubbed storage
    // keeps the initial read deterministic in every environment regardless
    // of happy-dom localStorage behavior.
    stubMapStorage();
    takePendingForceTool("host-a");
    const user = userEvent.setup();
    const onWebSearchChange = vi.fn();
    render(
      <ToolCatalogBar
        clientConfig={{ ...catalogConfig, slug: "occ" }}
        sessionKey="host-a"
        webSearchScope="web-scope"
        onWebSearchChange={onWebSearchChange}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(takePendingForceTool("host-a")).toBe("digisearch");
    await user.click(screen.getByRole("button", { name: "Vault" }));
    expect(takePendingForceTool("host-a")).toBe("digivault");
    const web = screen.getByRole("button", { name: "Web search" });
    expect(web.getAttribute("aria-pressed")).toBe("true");
    await user.click(web);
    expect(web.getAttribute("aria-pressed")).toBe("false");
    expect(onWebSearchChange).toHaveBeenCalledWith(false);
  });

  it("hides when the catalog is empty or toggles are disabled", () => {
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
    // Baseline (slug "embed", no stored pref): default-on.
    stubMapStorage();
    const { unmount } = render(
      <ToolCatalogBar
        clientConfig={catalogConfig}
        sessionKey="baseline-scope"
        webSearchScope="baseline-web-default"
      />,
    );
    expect(catalogConfig.slug).toBe("embed");
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
    expect(screen.getByRole("button", { name: "Search" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Vault" })).toBeDefined();
  });
});
