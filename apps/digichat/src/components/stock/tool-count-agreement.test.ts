/**
 * The count the composer toolbar prints and the rows `/tools` lists come from
 * one expansion (#tool-contract). They used to be computed twice and disagreed
 * on the same deployment: OCC read "7 tools" in the footer and listed 9.
 */

import { describe, expect, it } from "vitest";
import { connectedToolIsOn, countToolSurface } from "@digithings/ui/chat/tool-surface";
import { connectedTools } from "./embed-mcp-flow";

const tickets = {
  id: "tickets",
  tools: [
    { id: "tickets_search" },
    { id: "tickets_list" },
    { id: "tickets_get" },
    { id: "tickets_report" },
    { id: "tickets_aggregate" },
  ],
};

/** The OCC shape: three operator servers, nothing broken down but the ticket server. */
function occInput(over: { hasDigisearch?: boolean; hasVault?: boolean } = {}) {
  return {
    hasDigisearch: over.hasDigisearch ?? true,
    hasVault: over.hasVault ?? true,
    tenantAllowsWeb: false,
    catalogTools: [],
    mcpServers: [tickets, { id: "digisearch" }, { id: "digivault" }],
    mcpCustom: [],
  };
}

/** The tools `/tools` lists as switched on, read off its own rows. */
function menuEnabledTools(input: ReturnType<typeof occInput>): number {
  const switchInput = {
    digisearch: input.hasDigisearch,
    vault: input.hasVault,
    webSearch: input.tenantAllowsWeb,
    extraToolOn: () => true,
  };
  return connectedTools(input).reduce((total, row) => {
    if (!connectedToolIsOn(row.id, switchInput)) return total;
    return total + (row.tools?.length ?? row.builtinTools?.length ?? 0);
  }, 0);
}

function barCount(input: ReturnType<typeof occInput>) {
  return countToolSurface(input.mcpServers, {
    isOn: (id) =>
      connectedToolIsOn(id, {
        digisearch: input.hasDigisearch,
        vault: input.hasVault,
        webSearch: input.tenantAllowsWeb,
        extraToolOn: () => true,
      }),
    isToolOn: () => true,
  });
}

describe("the toolbar count matches the rows /tools lists", () => {
  it("counts every tool the menu has switched on", () => {
    const input = occInput();
    expect(barCount(input).tools).toBe(menuEnabledTools(input));
    // 5 tickets tools + the digisearch pair + the digivault pair.
    expect(barCount(input)).toEqual({ servers: 3, tools: 9 });
  });

  it("stays equal when a house switch is off", () => {
    const input = occInput({ hasVault: false });
    expect(barCount(input).tools).toBe(menuEnabledTools(input));
    expect(barCount(input)).toEqual({ servers: 2, tools: 7 });
  });

  it("stays equal when the deployment named the tools itself", () => {
    const input = {
      ...occInput(),
      mcpServers: [
        tickets,
        { id: "digisearch", tools: [{ id: "digisearch_semantic" }] },
        { id: "digivault" },
      ],
    };
    expect(barCount(input).tools).toBe(menuEnabledTools(input));
    expect(barCount(input)).toEqual({ servers: 3, tools: 8 });
  });
});
