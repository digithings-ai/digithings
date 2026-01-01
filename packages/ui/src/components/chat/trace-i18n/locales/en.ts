import type { TraceStrings } from "../types";

export const en: TraceStrings = {
  reasoning: "Reasoning",
  thinking: "Thinking",
  thought: "Thought",
  working: "Working",
  worked: "Worked",
  workingOn: "Working — {tool}",
  toolFallbackName: "tool",
  needsInput: "Needs your input",
  stopped: "Stopped",
  failed: "Failed",
  usedTools: { one: "Used {count} tool", other: "Used {count} tools" },
  thoughtAndUsedTools: { one: "Thought and used {count} tool", other: "Thought and used {count} tools" },
  toolCalls: { one: "{count} tool call", other: "{count} tool calls" },
  usedTool: "Used tool",
  cancelledTool: "Cancelled tool",
  failedTool: "Failed tool",
  runningTool: "Running tool",
  waitingOnTool: "Waiting on tool",
  errorPrefix: "Error:",
  cancelledPrefix: "Cancelled:",
};
