"use client";

/**
 * Local fixture runtime for the design-reference Thread specimen.
 * Streams MCP-shaped tools (digisearch / digivault / digiquant) so the
 * gallery looks like the website embed and the digiquant dashboard.
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
