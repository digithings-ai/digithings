// @vitest-environment happy-dom
"use client";

import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmbedComposerMenu } from "./embed-composer-menu";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  EmbedChatPrefsProvider,
  type EmbedChatPrefsApi,
} from "@digithings/ui/chat/stock";
import { toDigichatClientConfig } from "@/lib/deploy-config/client-projection";
import { expandDigichatDocument } from "@/lib/deploy-config/loader";
import { parseDigichatConfig } from "@/lib/deploy-config/schema";
import { expandDigichatDocument } from "@/lib/deploy-config/loader";
import { toolControlFor } from "@/lib/tool-control";

// The trial's /tools page, rendered from its real Foundry deployment yaml.
// Nothing here calls a model or the network.

/** Every tool the trial's Foundry agent is bound to, in its group order. */
const AGENT_TOOLS: ReadonlyArray<readonly string[]> = [
  [
    "list_connections",
    "connect_source",
    "connect_destination",
    "disconnect_connection",
    "discover_users",
    "discover_groups",
    "browse_source_items",
    "preview_item",
  ],
  [
    "list_collectors",
    "get_collector",
    "create_email_collector",
    "create_sharepoint_site_collector",
    "create_files_collector",
    "create_teams_collector",
    "run_collector",
    "stop_collector",
    "get_collector_status",
    "update_collector",
    "delete_collector",
  ],
  ["collect_email", "collect_sharepoint_site", "collect_files"],
  ["create_restore_job"],
  [
    "list_running_collectors",
    "get_running_collector_accounts",
    "list_collector_reports",
    "get_collector_report_accounts",
    "list_datamanagement_reports",
    "get_datamanagement_report_accounts",
    "get_collection_stats",
    "get_collection_summary",
  ],
  [
    "search_content",
    "count_content",
    "get_item",
    "search_content_advanced",
    "list_searchable_fields",
    "get_conversation_thread",
    "get_channel_thread",
    "find_related_items",
    "search_attachments",
    "summarize_content",
  ],
  ["azure_ai_search"],
];

function prefs(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
  return {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS },
    setWebSearch: vi.fn(),
    setDigisearch: vi.fn(),
    setVault: vi.fn(),
    setExtraTool: vi.fn(),
    extraToolOn: () => true,
    setMcpConfig: vi.fn(),
    removeMcpConfig: vi.fn(),
    setLanguage: vi.fn(),
    setView: vi.fn(),
    setThinking: vi.fn(),
    setModel: vi.fn(),
    setEffort: vi.fn(),
    setSearchEngine: vi.fn(),
    setToolbar: vi.fn(),
    setScrollbars: vi.fn(),
    setDensity: vi.fn(),
    reset: vi.fn(),
    tenantAllowsWeb: false,
    showByok: false,
    showModels: true,
    hasDigisearch: false,
    hasVault: false,
    hasSessions: false,
    hasArtifacts: false,
    allowUserMcp: false,
    allowAddMcp: false,
    catalogTools: [],
    mcpServers: [],
    sessionKey: "t",
    openSettings: vi.fn(),
    openHelp: vi.fn(),
    openTools: vi.fn(),
    openMcp: vi.fn(),
    openByok: vi.fn(),
    openModels: vi.fn(),
    openEffort: vi.fn(),
    openSearchEngine: vi.fn(),
    openView: vi.fn(),
    openDensity: vi.fn(),
    openThinking: vi.fn(),
    openLanguage: vi.fn(),
    openSessions: vi.fn(),
    openArtifacts: vi.fn(),
    newThread: vi.fn(),
    compactThread: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    setComposerDraft: vi.fn(),
    composerDraftBound: true,
    ...over,
  };
}

function mountHost() {
  const wrap = document.createElement("div");
  wrap.setAttribute("data-thread-skin", "digichat");
  wrap.innerHTML = `<div class="aui-composer-root"></div>`;
  document.body.appendChild(wrap);
}

/** The server id the foundry deployment names, read from its own document. */
let foundryServerId = "";

function trialClient() {
  const dir = resolve(__dirname, "../../../config");
  for (const name of readdirSync(dir)) {
    if (!name.endsWith(".yaml")) continue;
    const cfg = parseDigichatConfig(
      expandDigichatDocument(loadYaml(readFileSync(resolve(dir, name), "utf8"))),
      name,
    );
    const client = toDigichatClientConfig(cfg.deployment!);
    if (client.backendType === "foundry") {
      foundryServerId = client.tools.catalog[0]?.id ?? "";
      return client;
    }
  }
  throw new Error("no foundry deployment");
}

/**
 * The backend prefixes each MCP tool id with its server id; the row must show
 * that id, never the deployment's short tool label.
 */
const toolIdPrefix = (): string => {
  trialClient();
  if (!foundryServerId) throw new Error("the foundry deployment names no MCP server");
  return `${foundryServerId}__`;
};
const rawToolId = (name: string) => `${toolIdPrefix()}${name}`;

/** The expected page: the service, then each group heading and its tree. */
function expectedPage(service: string, groups: readonly string[]): string {
  const lines = [`${`/${service}`.padEnd(40)} On`];
  AGENT_TOOLS.forEach((names, g) => {
    lines.push(`  # ${groups[g]}`);
    names.forEach((name, i) => {
      const glyph = i === names.length - 1 ? "└─" : "├─";
      lines.push(`${`  ${glyph} ${rawToolId(name)}`.padEnd(40)} On`);
    });
  });
  return lines.join("\n");
}

/** The /tools page as text: headings, tree rows and each row's value. */
function toolsPage(): string {
  const menu = document.querySelector("button[id^='dc-menu-']")?.parentElement;
  if (!menu) return "";
  return Array.from(menu.children)
    .map((node) => {
      const el = node as HTMLElement;
      if (el.getAttribute("role") === "presentation") return `  # ${el.textContent ?? ""}`;
      if (!el.id.startsWith("dc-menu-")) return null;
      const glyph = el.querySelector("[data-slot='tools-tree-branch']")?.textContent ?? "";
      const label = el.querySelector("span.flex-1")?.textContent ?? "";
      const value = el.querySelector("span.ml-auto")?.textContent ?? "";
      const left = glyph ? `  ${glyph} ${label}` : label;
      return `${left.padEnd(40)} ${value}`.trimEnd();
    })
    .filter((line): line is string => line !== null)
    .join("\n");
}

describe("Foundry trial /tools", () => {
  beforeEach(mountHost);
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("lists every agent tool under its service, on and locked", async () => {
    const client = trialClient();
    const toolControl = toolControlFor({
      backendType: client.backendType,
      allowUserToggle: client.tools.allowUserToggle,
      lockSessionControls: client.gate.lockSessionControls,
    });
    expect(toolControl).toBe("agent");
    const api = prefs({
      toolControl,
      // A stored "off" must not show: the agent's tools are always on.
      extraToolOn: () => false,
      catalogTools: client.tools.catalog,
    });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="tools" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );

    const service = client.tools.catalog[0]!;
    const tools = service.tools ?? [];
    const groups = [...new Set(tools.map((tool) => tool.group ?? ""))];
    expect(groups).toHaveLength(AGENT_TOOLS.length);
    expect(tools.map((tool) => tool.label)).toEqual(AGENT_TOOLS.flat());
    // The rendered row is the backend id, not the deployment's short label.
    expect(tools.map((tool) => tool.id)).toEqual(AGENT_TOOLS.flat().map(rawToolId));
    expect(toolsPage()).toBe(expectedPage(service.id, groups));

    const rows = screen.getAllByRole("menuitemcheckbox");
    // The service plus its 42 tools, every one checked.
    expect(rows).toHaveLength(43);
    expect(rows.every((row) => row.getAttribute("aria-checked") === "true")).toBe(true);
    expect(document.body.textContent ?? "").not.toMatch(/managed by/i);

    const user = userEvent.setup();
    await user.click(screen.getByRole("menuitemcheckbox", { name: new RegExp(`^/${service.id}`) }));
    await user.click(
      screen.getByRole("menuitemcheckbox", { name: new RegExp(`^${rawToolId("delete_collector")}`) }),
    );
    expect(api.setExtraTool).not.toHaveBeenCalled();
    expect(
      screen
        .getByRole("menuitemcheckbox", { name: new RegExp(`^${rawToolId("delete_collector")}`) })
        .getAttribute("aria-checked"),
    ).toBe("true");
  });
});
