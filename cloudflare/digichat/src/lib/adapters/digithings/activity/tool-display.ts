/** Raw backend tool ids for tool-row titles (one-to-one with the backend). */

export function toolRowTitle(toolName: string): string {
  const name = toolName.trim();
  return name || "tool";
}
