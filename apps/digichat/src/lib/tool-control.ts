/**
 * Who may flip a tool in `/tools`.
 *
 * Foundry tools live on the agent, so the pane lists them and does not toggle.
 * A host lock (`lockSessionControls`, or `allowUserToggle: false`) lists
 * every tool and MCP server but leaves the switch off.
 */

export type ToolControl = "toggle" | "locked" | "agent";

export function toolControlFor(input: {
  backendType?: string;
  lockSessionControls?: boolean;
  allowUserToggle?: boolean;
}): ToolControl {
  if (input.backendType === "foundry") return "agent";
  if (input.lockSessionControls === true) return "locked";
  if (input.allowUserToggle === false) return "locked";
  return "toggle";
}
