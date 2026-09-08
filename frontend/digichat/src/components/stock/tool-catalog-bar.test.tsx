// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToolCatalogBar } from "./tool-catalog-bar";
import { DEFAULT_CLIENT_CONFIG } from "@/lib/deploy-config";
import { takePendingForceTool } from "@/lib/pending-chat-headers";

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
  it("arms X-Digi-Force-Tool on Search / Vault and isolates web search prefs", async () => {
    takePendingForceTool("host-a");
    const user = userEvent.setup();
    const onWebSearchChange = vi.fn();
    render(
      <ToolCatalogBar
        clientConfig={catalogConfig}
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
    expect(web.getAttribute("aria-pressed")).toBe("false");
    await user.click(web);
    expect(web.getAttribute("aria-pressed")).toBe("true");
    expect(onWebSearchChange).toHaveBeenCalledWith(true);
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
});
