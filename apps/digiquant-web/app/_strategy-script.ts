/**
 * Scripted digichat session for the landing band.
 *
 * Tool names and argument names are the ones registered in
 * digiquant/src/digiquant/mcp_server.py. `AAPL` is the example symbol from
 * the tool docstring; `ema_cross` is a registered strategy.
 *
 * Every tool result is a scripted demo. It names no price, P&L, or NAV,
 * and it says so in the payload. The player withholds a result until that
 * call has settled, so the real thread can show the call as running.
 */

export const STRATEGY_THREAD_ID = "scripted-story";
export const STRATEGY_THREAD_TITLE = "scripted story";

const DEMO = "scripted demo — not a house book read";

export type ScriptTool = {
  kind: "tool";
  callId: string;
  name: string;
  args: Record<string, string>;
  result: Record<string, string>;
};

export type ScriptPart = { kind: "text"; text: string } | ScriptTool;

export type ScriptTurn =
  | { role: "user"; id: string; text: string }
  | { role: "assistant"; id: string; parts: readonly ScriptPart[] };

export const STRATEGY_TURNS: readonly ScriptTurn[] = [
  {
    role: "user",
    id: "user-build",
    text: "Build me a simple trend-following strategy. What can I start from?",
  },
  {
    role: "assistant",
    id: "assistant-chain",
    parts: [
      {
        kind: "text",
        text: "This scripted story is not a live session and is not connected to any MCP server. I'll walk a trend-following idea through the registry, a backtest, and an optimize as one tool chain. Each result is a scripted demo, not a house book read.",
      },
      {
        kind: "tool",
        callId: "call-list",
        name: "digiquant_list_strategies",
        args: {},
        result: { label: DEMO, registered: "ema_cross" },
      },
      {
        kind: "tool",
        callId: "call-backtest",
        name: "digiquant_run_backtest",
        args: { strategy_name: "ema_cross", symbols_json: '["AAPL"]' },
        result: {
          label: DEMO,
          strategy: "ema_cross",
          symbols: "AAPL",
          status: "completed in this script",
        },
      },
      {
        kind: "tool",
        callId: "call-optimize",
        name: "digiquant_run_optimize",
        args: { strategy_name: "ema_cross", symbols_json: '["AAPL"]', method: "grid" },
        result: {
          label: DEMO,
          strategy: "ema_cross",
          method: "grid",
          status: "completed in this script",
        },
      },
      {
        kind: "text",
        text: "The chain finished in this script. Exporting writes a file, so that step waits for a go-ahead. Nothing is deployed and nothing trades.",
      },
    ],
  },
  {
    role: "user",
    id: "user-export",
    text: "Go ahead and export it.",
  },
  {
    role: "assistant",
    id: "assistant-export",
    parts: [
      {
        kind: "tool",
        callId: "call-export",
        name: "digiquant_export",
        args: { strategy_name: "ema_cross", target: "review file" },
        result: {
          label: DEMO,
          strategy: "ema_cross",
          target: "review file",
          deployed: "no",
          trading: "no",
        },
      },
      {
        kind: "text",
        text: "A review file was written in this script. It is not a house book read, and nothing trades.",
      },
    ],
  },
];

type TextPart = { readonly type: "text"; readonly text: string };
type ToolPart = {
  readonly type: "tool-call";
  readonly toolCallId: string;
  readonly toolName: string;
  readonly args: Record<string, string>;
  readonly argsText: string;
  readonly result?: Record<string, string>;
};

export type ScriptMessage = {
  readonly id: string;
  readonly role: "user" | "assistant";
  readonly content: string | readonly (TextPart | ToolPart)[];
  readonly status?: { readonly type: "running" } | { readonly type: "complete"; readonly reason: "stop" };
};

export type PlayCursor = {
  /** First turn that is not yet fully revealed. */
  turn: number;
  part: number;
  chars: number;
  /** Current tool is on screen with its result withheld. */
  holding: boolean;
};

export const PLAY_START: PlayCursor = { turn: 0, part: 0, chars: 0, holding: false };
export const PLAY_DONE: PlayCursor = {
  turn: STRATEGY_TURNS.length,
  part: 0,
  chars: 0,
  holding: false,
};

const TEXT_CHARS = 2;
const TEXT_TICK_MS = 32;
const TOOL_RUN_MS = 680;
const USER_HOLD_MS = 420;
const TURN_GAP_MS = 360;

function toolPart(tool: ScriptTool, withResult: boolean): ToolPart {
  const part: ToolPart = {
    type: "tool-call",
    toolCallId: tool.callId,
    toolName: tool.name,
    args: tool.args,
    argsText: JSON.stringify(tool.args),
  };
  return withResult ? { ...part, result: tool.result } : part;
}

function completeTurn(turn: ScriptTurn): ScriptMessage {
  if (turn.role === "user") {
    return { id: turn.id, role: "user", content: turn.text };
  }
  return {
    id: turn.id,
    role: "assistant",
    status: { type: "complete", reason: "stop" },
    content: turn.parts.map((part) =>
      part.kind === "text" ? { type: "text" as const, text: part.text } : toolPart(part, true),
    ),
  };
}

/** Messages visible at `cursor`. A tool result is omitted while that call is holding. */
export function project(cursor: PlayCursor): { messages: ScriptMessage[]; running: boolean } {
  const messages: ScriptMessage[] = [];
  const revealed = Math.min(cursor.turn, STRATEGY_TURNS.length);
  for (let i = 0; i < revealed; i += 1) {
    const turn = STRATEGY_TURNS[i];
    if (turn) messages.push(completeTurn(turn));
  }
  if (cursor.turn >= STRATEGY_TURNS.length) return { messages, running: false };

  const turn = STRATEGY_TURNS[cursor.turn];
  if (!turn || turn.role === "user") return { messages, running: false };

  const content: (TextPart | ToolPart)[] = [];
  for (let p = 0; p < turn.parts.length; p += 1) {
    const part = turn.parts[p];
    if (!part) continue;
    if (p < cursor.part) {
      content.push(part.kind === "text" ? { type: "text", text: part.text } : toolPart(part, true));
      continue;
    }
    if (p !== cursor.part) break;
    if (part.kind === "text") {
      const slice = part.text.slice(0, cursor.chars);
      if (slice.trim()) content.push({ type: "text", text: slice });
    } else if (cursor.holding) {
      content.push(toolPart(part, false));
    }
  }

  if (content.length === 0) return { messages, running: true };
  messages.push({
    id: turn.id,
    role: "assistant",
    status: { type: "running" },
    content,
  });
  return { messages, running: true };
}

export function nextCursor(cursor: PlayCursor): { cursor: PlayCursor; delay: number; done: boolean } {
  if (cursor.turn >= STRATEGY_TURNS.length) return { cursor, delay: 0, done: true };
  const turn = STRATEGY_TURNS[cursor.turn];
  if (!turn) return { cursor: PLAY_DONE, delay: 0, done: true };
  if (turn.role === "user") {
    const next = cursor.turn + 1;
    return {
      cursor: { turn: next, part: 0, chars: 0, holding: false },
      delay: USER_HOLD_MS,
      done: next >= STRATEGY_TURNS.length,
    };
  }
  const part = turn.parts[cursor.part];
  if (!part) {
    const next = cursor.turn + 1;
    return {
      cursor: { turn: next, part: 0, chars: 0, holding: false },
      delay: TURN_GAP_MS,
      done: next >= STRATEGY_TURNS.length,
    };
  }
  if (part.kind === "text") {
    const chars = Math.min(part.text.length, cursor.chars + TEXT_CHARS);
    if (chars >= part.text.length) {
      return {
        cursor: { turn: cursor.turn, part: cursor.part + 1, chars: 0, holding: false },
        delay: TEXT_TICK_MS,
        done: false,
      };
    }
    return {
      cursor: { turn: cursor.turn, part: cursor.part, chars, holding: false },
      delay: TEXT_TICK_MS,
      done: false,
    };
  }
  if (!cursor.holding) {
    return {
      cursor: { turn: cursor.turn, part: cursor.part, chars: 0, holding: true },
      delay: TOOL_RUN_MS,
      done: false,
    };
  }
  return {
    cursor: { turn: cursor.turn, part: cursor.part + 1, chars: 0, holding: false },
    delay: 160,
    done: false,
  };
}
