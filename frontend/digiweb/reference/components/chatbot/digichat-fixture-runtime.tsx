"use client";

/**
 * Local fixture runtime for the design-reference Thread specimen.
 * Streams a canned assistant turn (reasoning → tool → markdown) so the
 * registry Thread can be walked without a backend.
 */
import {
  AuiConfig,
  AssistantRuntimeProvider,
  CompositeAttachmentAdapter,
  SimpleImageAttachmentAdapter,
  SimpleTextAttachmentAdapter,
  Suggestions,
  useLocalRuntime,
  type ChatModelAdapter,
} from "@assistant-ui/react";
import { useSyncExternalStore, type ReactNode } from "react";

const REPLY = `Done — trend_xsec (time-series), 8y ETH-USD, Kelly-capped 0.5×.

| metric | value |
| --- | --- |
| PF | **2.31** |
| max DD | −18.4% |

\`\`\`python
bt = Backtest("trend_xsec", symbol="ETH-USD")
bt.run(years=8)
\`\`\`
`;

const REASONING = [
  "Single-symbol request — fall back to the time-series variant.",
  "Cap sizing with Kelly at 0.5× so the drawdown stays bounded.",
].join("\n");

const adapter: ChatModelAdapter = {
  async *run({ abortSignal }) {
    // Hold on the cube matrix before any parts land.
    await pause(2200, abortSignal);

    const reasoningStep = 8;
    for (let end = reasoningStep; ; end += reasoningStep) {
      if (abortSignal.aborted) return;
      yield {
        content: [
          {
            type: "reasoning" as const,
            text: REASONING.slice(0, Math.min(end, REASONING.length)),
          },
        ],
      };
      if (end >= REASONING.length) break;
      await pause(70, abortSignal);
    }

    await pause(900, abortSignal);

    const tool = {
      type: "tool-call" as const,
      toolCallId: "bt-1",
      toolName: "digiquant.backtest",
      args: { symbol: "ETH-USD", years: 8 },
      argsText: "trend_xsec · ETH-USD · 8y",
    };

    yield {
      content: [{ type: "reasoning" as const, text: REASONING }, tool],
    };
    await pause(1100, abortSignal);

    const toolDone = { ...tool, result: "PF 2.31 · maxDD −18.4%" };
    yield {
      content: [
        { type: "reasoning" as const, text: REASONING },
        toolDone,
        { type: "text" as const, text: "" },
      ],
    };
    await pause(450, abortSignal);

    const STEP = 10;
    for (let end = STEP; ; end += STEP) {
      if (abortSignal.aborted) return;
      yield {
        content: [
          { type: "reasoning" as const, text: REASONING },
          toolDone,
          { type: "text" as const, text: REPLY.slice(0, Math.min(end, REPLY.length)) },
        ],
      };
      if (end >= REPLY.length) break;
      await pause(55, abortSignal);
    }
  },
};

function pause(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const t = window.setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(t);
        reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

type WelcomeSuggestion =
  | string
  | { title: string; label?: string; prompt: string };

/** Opt-in welcome starters. Empty = no chips (default template). */
const DEFAULT_CHIPS: readonly WelcomeSuggestion[] = [];

const subscribe = () => () => {};
const clientMounted = () => true;
const serverMounted = () => false;

export function DigichatFixtureRuntime({
  children,
  suggestions = DEFAULT_CHIPS,
}: {
  children: ReactNode;
  suggestions?: readonly WelcomeSuggestion[];
}) {
  const mounted = useSyncExternalStore(subscribe, clientMounted, serverMounted);
  if (!mounted) {
    return (
      <div
        className="flex min-h-[12rem] items-center px-[1.15rem] font-mono text-[0.74rem] text-term-mute"
        aria-busy="true"
      >
        loading thread…
      </div>
    );
  }
  return (
    <DigichatFixtureRuntimeInner suggestions={suggestions}>{children}</DigichatFixtureRuntimeInner>
  );
}

function DigichatFixtureRuntimeInner({
  children,
  suggestions,
}: {
  children: ReactNode;
  suggestions: readonly WelcomeSuggestion[];
}) {
  const runtime = useLocalRuntime(adapter, {
    adapters: {
      attachments: new CompositeAttachmentAdapter([
        new SimpleImageAttachmentAdapter(),
        new SimpleTextAttachmentAdapter(),
      ]),
    },
  });
  const config =
    suggestions.length > 0
      ? AuiConfig({ suggestions: Suggestions([...suggestions]) })
      : AuiConfig({});
  return (
    <AssistantRuntimeProvider runtime={runtime} config={config}>
      {children}
    </AssistantRuntimeProvider>
  );
}
