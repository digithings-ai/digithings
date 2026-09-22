"use client";

/**
 * Local fixture runtime for the landing-page digichat simulation (#4429,
 * Stage 8, point 13).
 *
 * Ported from the design reference's `digichat-fixture-runtime.tsx` — it lives
 * under `apps/reference`, which must not become a runtime dependency of the
 * site. It streams MCP-shaped tool calls (digisearch / digivault) so the Thread
 * draws the real tool rows, reasoning trace and markdown of the product
 * conversation, with no backend and no container.
 *
 * This is a **simulation**. Nothing here is connected to digichat. The landing
 * page intercepts every send and routes to /chat (see `QuickAsk.tsx`), so the
 * adapter exists to satisfy `useLocalRuntime` and to keep the pane honest if a
 * turn ever does run: the canned scenarios cite real doc paths and state no
 * figure.
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
  type SuggestionConfig,
} from "@assistant-ui/react";
import { useSyncExternalStore, type ReactNode } from "react";

import { lastUserText, pickFixtureScenario, type FixtureTool } from "./digichat-fixture-scenarios";

function asToolPart(tool: FixtureTool, result?: string) {
  return {
    type: "tool-call" as const,
    toolCallId: tool.toolCallId,
    toolName: tool.toolName,
    args: tool.args,
    argsText: tool.argsText,
    ...(result !== undefined
      ? { result, status: { type: "complete" as const } }
      : { status: { type: "running" as const } }),
  };
}

const adapter = {
  async *run({ messages, abortSignal }) {
    const scenario = pickFixtureScenario(lastUserText(messages));
    await pause(900, abortSignal);

    const reasoningStep = 10;
    for (let end = reasoningStep; ; end += reasoningStep) {
      if (abortSignal.aborted) return;
      yield {
        content: [
          {
            type: "reasoning" as const,
            text: scenario.reasoning.slice(0, Math.min(end, scenario.reasoning.length)),
          },
        ],
      };
      if (end >= scenario.reasoning.length) break;
      await pause(55, abortSignal);
    }

    const settled: ReturnType<typeof asToolPart>[] = [];
    for (const tool of scenario.tools) {
      await pause(700, abortSignal);
      yield {
        content: [
          { type: "reasoning" as const, text: scenario.reasoning },
          ...settled,
          asToolPart(tool),
        ],
      };
      await pause(900, abortSignal);
      settled.push(asToolPart(tool, tool.result));
      yield {
        content: [
          { type: "reasoning" as const, text: scenario.reasoning },
          ...settled,
        ],
      };
    }

    await pause(350, abortSignal);
    const STEP = 12;
    for (let end = STEP; ; end += STEP) {
      if (abortSignal.aborted) return;
      yield {
        content: [
          { type: "reasoning" as const, text: scenario.reasoning },
          ...settled,
          { type: "text" as const, text: scenario.reply.slice(0, Math.min(end, scenario.reply.length)) },
        ],
      };
      if (end >= scenario.reply.length) break;
      await pause(40, abortSignal);
    }
  },
} as ChatModelAdapter;

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

function toSuggestionConfig(item: WelcomeSuggestion): SuggestionConfig {
  if (typeof item === "string") return item;
  return { title: item.title, label: item.label ?? "", prompt: item.prompt };
}

const subscribe = () => () => {};
const clientMounted = () => true;
const serverMounted = () => false;

export function DigichatFixtureRuntime({
  children,
  suggestions = [],
}: {
  children: ReactNode;
  suggestions?: readonly WelcomeSuggestion[];
}) {
  /* localStorage-free hydration signal: the runtime is client-only, and a
     mount effect whose sole job is a synchronous setState is the pattern this
     replaces. */
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
      ? AuiConfig({
          suggestions: Suggestions(suggestions.map(toSuggestionConfig)),
        })
      : AuiConfig({});
  return (
    <AssistantRuntimeProvider runtime={runtime} config={config}>
      {children}
    </AssistantRuntimeProvider>
  );
}
