/**
 * Example digichat threads for the marketing chat band.
 *
 * Tool names and argument names are the ones the MCP servers register:
 * digiquant (`mcp_server.py`), digisearch (`web_search`, `grokipedia_search`,
 * `grokipedia_get_page`), and digivault (`create_note`, `search_notes`).
 * `ema_cross` defaults (fast 10, slow 20) are the registered strategy.
 * `AAPL` is the example symbol from the backtest tool docstring.
 *
 * No house-book print. Performance fields stay off the payload.
 */

export const EXAMPLE_ORDER = ["strategy", "research", "journal", "digest"] as const;

export type ExampleId = (typeof EXAMPLE_ORDER)[number];

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

export type ExampleThread = {
  id: ExampleId;
  title: string;
  turns: readonly ScriptTurn[];
};

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

export type TourState = {
  id: ExampleId;
  cursor: PlayCursor;
};

const TEXT_CHARS = 2;
const TEXT_TICK_MS = 32;
const TOOL_RUN_MS = 680;
const USER_HOLD_MS = 420;
const TURN_GAP_MS = 360;
/** Finished example stays up, then the tour opens the next sidebar chat. */
export const TOUR_HOLD_MS = 1400;

function say(text: string): ScriptPart {
  return { kind: "text", text };
}

function tool(
  callId: string,
  name: string,
  args: Record<string, string>,
  result: Record<string, string>,
): ScriptTool {
  return { kind: "tool", callId, name, args, result };
}

function user(id: string, text: string): ScriptTurn {
  return { role: "user", id, text };
}

function assistant(id: string, parts: readonly ScriptPart[]): ScriptTurn {
  return { role: "assistant", id, parts };
}

const STRATEGY_TURNS: readonly ScriptTurn[] = [
  user("strategy-user", "How do I start a trend-following strategy?"),
  assistant("strategy-assistant", [
    say("I'll look up the trend indicators, then the pieces of a registered strategy that uses them."),
    tool(
      "call-technicals",
      "digiquant_get_price_technicals",
      { ticker: "AAPL", lookback: "20" },
      {
        ticker: "AAPL",
        lookback: "20",
        indicators: "ema_12, ema_26, ema_50, macd, adx_14",
      },
    ),
    say("The technicals set already carries the trend stack: ema_12, ema_26, ema_50, macd, and adx_14."),
    tool(
      "call-list",
      "digiquant_list_strategies",
      {},
      {
        name: "ema_cross",
        description: "EMA crossover, market orders (Nautilus EMACross)",
        fast_ema_period: "10",
        slow_ema_period: "20",
        trade_size: "1000",
      },
    ),
    say(
      "ema_cross is the starting point. It is an EMA crossover with market orders. The components are a fast EMA of 10, a slow EMA of 20, and the trade size.",
    ),
    say(
      "Those indicators are viable for that cross. The fast length is shorter than the slow length, and both sit next to averages the technicals set already computes.",
    ),
    tool(
      "call-optimize",
      "digiquant_run_optimize",
      { strategy_name: "ema_cross", symbols_json: '["AAPL"]', method: "grid" },
      {
        strategy_name: "ema_cross",
        symbols: "AAPL",
        method: "grid",
        fast_ema_period: "10",
        slow_ema_period: "20",
        status: "ok",
      },
    ),
    say(
      "The optimization pass used a grid over the registered ranges. The set it posts is the registered default: fast 10, slow 20.",
    ),
    tool(
      "call-backtest",
      "digiquant_run_backtest",
      {
        strategy_name: "ema_cross",
        symbols_json: '["AAPL"]',
        strategy_params_json: '{"fast_ema_period":10,"slow_ema_period":20}',
      },
      {
        strategy_name: "ema_cross",
        symbols: "AAPL",
        status: "ok",
        fast_ema_period: "10",
        slow_ema_period: "20",
        message: "Backtest completed",
      },
    ),
    say(
      "Backtest results for ema_cross on AAPL. Status ok. Fast EMA 10, slow EMA 20, market orders. That is the run the tool just posted.",
    ),
  ]),
];

const RESEARCH_TURNS: readonly ScriptTurn[] = [
  user(
    "research-user",
    "A major central bank shifted its policy rate this week. At a high level, what does that mean for markets?",
  ),
  assistant("research-assistant", [
    say("I'll pull a web search and Grokopedia, then write the note."),
    tool(
      "call-web",
      "web_search",
      { query: "central bank policy rate change effect on markets" },
      {
        query: "central bank policy rate change effect on markets",
        title: "Policy rates and market transmission",
        snippet:
          "A policy-rate change moves funding costs, the currency, and the discount rate on equities and credit.",
        tier: "External",
      },
    ),
    tool(
      "call-grok-search",
      "grokipedia_search",
      { query: "monetary policy transmission", limit: "5" },
      {
        query: "monetary policy transmission",
        slug: "Monetary_policy",
        title: "Monetary policy",
      },
    ),
    tool(
      "call-grok-page",
      "grokipedia_get_page",
      { slug: "Monetary_policy", include_content: "true" },
      {
        slug: "Monetary_policy",
        title: "Monetary policy",
        found: "true",
        content:
          "A policy-rate shift passes through funding costs, the currency, and the discount rate used for equities and credit. The high-level read is the direction of real yields.",
      },
    ),
    say(
      "Research note. The web search and the Grokopedia page on monetary policy agree on the transmission: funding costs, the currency, and the discount rate on equities and credit move first. For markets, watch the direction of real yields and whether growth or inflation is the stated reason.",
    ),
  ]),
];

const JOURNAL_NOTE =
  "Bought the EMA cross and felt late. Slow average still rising. Idea: only take the cross when the slow average is rising.";

const JOURNAL_TURNS: readonly ScriptTurn[] = [
  user(
    "journal-user",
    "Journal this. I bought the EMA cross and felt late. The slow average is still rising, so I think the trend holds. Idea to bounce: only take the cross when the slow average is rising.",
  ),
  assistant("journal-save", [
    say(
      "Saving that to digichat memory on the trader profile: the trade, the late feeling, the view that the slow average still rises, and the idea to take the cross only when it is rising.",
    ),
    tool(
      "call-note",
      "create_note",
      {
        name: "trader-profile",
        title: "trader profile",
        path_prefix: "trader-profile",
        body: JOURNAL_NOTE,
      },
      {
        name: "trader-profile",
        title: "trader profile",
        path_prefix: "trader-profile",
      },
    ),
    say("Stored. The trader profile now holds that note in digichat memory."),
  ]),
  user("journal-pipeline", "When a pipeline runs later, have it read that memory."),
  assistant("journal-run", [
    say("Reading the trader profile back, then running the pipeline with that note in the thread."),
    tool(
      "call-search",
      "search_notes",
      { query: "trader profile", path_prefix: "trader-profile" },
      {
        name: "trader-profile",
        title: "trader profile",
        excerpt: JOURNAL_NOTE,
      },
    ),
    tool(
      "call-pipeline",
      "digiquant_run_pipeline",
      {
        strategy_name: "ema_cross",
        symbols_json: '["AAPL"]',
        run_optimize: "true",
        run_export: "false",
      },
      {
        strategy_name: "ema_cross",
        symbols: "AAPL",
        status: "ok",
        trace: "validate, backtest, optimize",
      },
    ),
    say(
      "search_notes returned the trader profile. digiquant_run_pipeline then runs ema_cross on AAPL through validate, backtest, and optimize, and the run can read that memory from the thread.",
    ),
  ]),
];

const DIGEST_TURNS: readonly ScriptTurn[] = [
  user("digest-user", "Send the daily digest."),
  assistant("digest-assistant", [
    say("Pulling today's brief."),
    tool(
      "call-brief",
      "digiquant_query_research",
      { dataset: "daily_snapshots", run_type: "baseline", phase: "research_edit" },
      {
        dataset: "daily_snapshots",
        phase: "research_edit",
        status: "ok",
        brief: "The daily snapshot is the brief: the day's research note, and what changed since the prior run.",
      },
    ),
    say(
      "Daily digest. The brief is the daily snapshot. It carries the day's research note and what changed since the prior run.",
    ),
  ]),
];

export const EXAMPLES: readonly ExampleThread[] = [
  { id: "strategy", title: "Trend-following strategy", turns: STRATEGY_TURNS },
  { id: "research", title: "World event research", turns: RESEARCH_TURNS },
  { id: "journal", title: "Trade journal", turns: JOURNAL_TURNS },
  { id: "digest", title: "Daily digest", turns: DIGEST_TURNS },
];

const BY_ID = new Map(EXAMPLES.map((example) => [example.id, example]));

export function isExampleId(id: string | undefined): id is ExampleId {
  return BY_ID.has(id as ExampleId);
}

export function exampleById(id: string): ExampleThread {
  return BY_ID.get(id as ExampleId) ?? EXAMPLES[0];
}

export const PLAY_START: PlayCursor = { turn: 0, part: 0, chars: 0, holding: false };

/** User line is already on screen. The assistant streams from here. */
export function openCursor(): PlayCursor {
  return { turn: 1, part: 0, chars: 0, holding: false };
}

export function doneCursor(turns: readonly ScriptTurn[]): PlayCursor {
  return { turn: turns.length, part: 0, chars: 0, holding: false };
}

function toolPart(entry: ScriptTool, withResult: boolean): ToolPart {
  const part: ToolPart = {
    type: "tool-call",
    toolCallId: entry.callId,
    toolName: entry.name,
    args: entry.args,
    argsText: JSON.stringify(entry.args),
  };
  return withResult ? { ...part, result: entry.result } : part;
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
export function projectTurns(
  turns: readonly ScriptTurn[],
  cursor: PlayCursor,
): { messages: ScriptMessage[]; running: boolean } {
  const messages: ScriptMessage[] = [];
  const revealed = Math.min(cursor.turn, turns.length);
  for (let i = 0; i < revealed; i += 1) {
    const turn = turns[i];
    if (turn) messages.push(completeTurn(turn));
  }
  if (cursor.turn >= turns.length) return { messages, running: false };

  const turn = turns[cursor.turn];
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

export function nextCursorFor(
  turns: readonly ScriptTurn[],
  cursor: PlayCursor,
): { cursor: PlayCursor; delay: number; done: boolean } {
  if (cursor.turn >= turns.length) {
    return { cursor: doneCursor(turns), delay: 0, done: true };
  }
  const turn = turns[cursor.turn];
  if (!turn) return { cursor: doneCursor(turns), delay: 0, done: true };
  if (turn.role === "user") {
    const next = cursor.turn + 1;
    return {
      cursor: { turn: next, part: 0, chars: 0, holding: false },
      delay: USER_HOLD_MS,
      done: next >= turns.length,
    };
  }
  const part = turn.parts[cursor.part];
  if (!part) {
    const next = cursor.turn + 1;
    return {
      cursor: { turn: next, part: 0, chars: 0, holding: false },
      delay: TURN_GAP_MS,
      done: next >= turns.length,
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

/** One tour tick. A finished chat is held, then the next sidebar chat opens. */
export function stepTour(state: TourState): { state: TourState; delay: number } {
  const example = exampleById(state.id);
  if (state.cursor.turn >= example.turns.length) {
    const index = EXAMPLE_ORDER.indexOf(example.id);
    const nextId = EXAMPLE_ORDER[(index + 1) % EXAMPLE_ORDER.length] ?? EXAMPLE_ORDER[0];
    return { state: { id: nextId, cursor: openCursor() }, delay: 280 };
  }
  const step = nextCursorFor(example.turns, state.cursor);
  return {
    state: { id: example.id, cursor: step.cursor },
    delay: step.done ? TOUR_HOLD_MS : step.delay,
  };
}

const YIELD_TYPES = new Set(["pointerdown", "wheel", "keydown"]);

/** A click, key, or wheel takes over. Hover takes over only on a control. */
export function shouldTakeOver(event: { isTrusted: boolean; type: string; control: boolean }): boolean {
  if (!event.isTrusted) return false;
  if (YIELD_TYPES.has(event.type)) return true;
  return event.type === "pointerover" && event.control;
}
