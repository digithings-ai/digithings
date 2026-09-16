// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { isToolUIPart, readUIMessageStream, type UIMessage, type UIMessageChunk } from "ai";
import {
  createActivityWriteContext,
  finishStandardActivity,
  writeStandardActivity,
} from "@/lib/ui-stream-parts";
import {
  ToolFallback,
  ToolFallbackAttribution,
  formatToolDuration,
} from "./tool-fallback.aui";

/** Feed the exact chunks the adapter emits for an orphaned tool row through the
 * AI SDK runtime conversion, as a real client does. */
async function readOrphanedToolMessage(): Promise<UIMessage> {
  const chunks: UIMessageChunk[] = [];
  const writer = { write: (chunk: UIMessageChunk) => chunks.push(chunk) };
  const ctx = createActivityWriteContext();
  writeStandardActivity(
    writer,
    {
      operation: "execute_tool",
      status: "started",
      label: "digivault_get_note",
      toolName: "digivault_get_note",
      toolInput: { vault_paths: ["clients/digithings/a.md"] },
    },
    ctx,
  );
  finishStandardActivity(writer, ctx);
  const stream = new ReadableStream<UIMessageChunk>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
  let message: UIMessage | undefined;
  for await (const next of readUIMessageStream({ stream })) message = next;
  return message as UIMessage;
}

describe("stock ToolFallback", () => {
  it("renders the digisearch row with the raw backend id", () => {
    render(
      <ToolFallback
        type="tool-call"
        toolCallId="t1"
        toolName="digisearch"
        args={{ query: "jwt", mode: "keyword" }}
        argsText='{"query":"jwt","mode":"keyword"}'
        status={{ type: "complete" }}
        addResult={() => undefined}
        resume={() => undefined}
        respondToApproval={async () => undefined}
      />,
    );
    expect(screen.getByText("digisearch")).toBeTruthy();
    expect(screen.queryByText("digisearch keyword")).toBeNull();
  });

  it("renders vault tool ids verbatim in the row title", () => {
    render(
      <ToolFallback
        type="tool-call"
        toolCallId="t2"
        toolName="digivault_get_note"
        args={{ vault_paths: ["a.md"] }}
        argsText='{"vault_paths":["a.md"]}'
        status={{ type: "complete" }}
        addResult={() => undefined}
        resume={() => undefined}
        respondToApproval={async () => undefined}
      />,
    );
    expect(screen.getByText("digivault_get_note")).toBeTruthy();
    expect(screen.queryByText("digivault get note")).toBeNull();
  });

  it("shows a failed row, not success, when the runtime reports an output-error", async () => {
    const message = await readOrphanedToolMessage();
    const toolPart = message.parts.find(isToolUIPart);
    // The runtime conversion must surface the orphan as an error part...
    expect(toolPart?.state).toBe("output-error");

    const toolName =
      toolPart && "toolName" in toolPart ? toolPart.toolName : "digivault_get_note";

    // ...and the renderer receives exactly the props the runtime derives:
    // isError true, result defined, and (per toMessagePartStatus) status
    // `complete` — the status must not be trusted as success on its own.
    render(
      <ToolFallback
        type="tool-call"
        toolCallId={toolPart?.toolCallId ?? "t3"}
        toolName={toolName}
        args={{ vault_paths: ["clients/digithings/a.md"] }}
        argsText='{"vault_paths":["clients/digithings/a.md"]}'
        result={
          toolPart && "errorText" in toolPart
            ? { error: toolPart.errorText }
            : undefined
        }
        status={{ type: "complete" }}
        isError={toolPart?.state === "output-error"}
        addResult={() => undefined}
        resume={() => undefined}
        respondToApproval={async () => undefined}
      />,
    );
    expect(screen.getByText(/Failed tool/)).toBeTruthy();
    expect(screen.queryByText(/Used tool/)).toBeNull();
  });
});

describe("stock formatToolDuration", () => {
  it("shows bare milliseconds under one second", () => {
    expect(formatToolDuration(0)).toBe("0ms");
    expect(formatToolDuration(412)).toBe("412ms");
    expect(formatToolDuration(999)).toBe("999ms");
  });

  it("shows dual-unit seconds and milliseconds at 1s and above", () => {
    expect(formatToolDuration(1000)).toBe("1.0s (1000ms)");
    expect(formatToolDuration(2300)).toBe("2.3s (2300ms)");
    expect(formatToolDuration(65000)).toBe("1m 5s (65000ms)");
  });
});

describe("stock ToolFallbackAttribution", () => {
  it("renders the source line, delay notice, and terminal deep link", () => {
    render(
      <ToolFallbackAttribution
        result={{
          result: {
            attribution: "Sourced from Gloomberb",
            delay_notice: "Data delayed up to 15 minutes",
            source_url: "https://term.gloom.sh/?ticker=AAPL",
          },
          durationMs: 12,
        }}
      />,
    );
    expect(screen.getByText("Sourced from Gloomberb")).toBeTruthy();
    expect(screen.getByText(/Data delayed up to 15 minutes/)).toBeTruthy();
    const link = screen.getByRole("link", { name: /Open in Gloomberb/ });
    expect(link.getAttribute("href")).toBe("https://term.gloom.sh/?ticker=AAPL");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("renders the source line without a link when no single listing was addressed", () => {
    render(
      <ToolFallbackAttribution
        result={{
          result: {
            attribution: "Sourced from Gloomberb",
            delay_notice: "Data delayed up to 15 minutes",
          },
        }}
      />,
    );
    expect(screen.getByText("Sourced from Gloomberb")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("renders nothing for an unattributed tool result", () => {
    const { container } = render(
      <ToolFallbackAttribution
        result={{ result: { rows: [{ symbol: "AAPL" }] }, durationMs: 4 }}
      />,
    );
    expect(
      container.querySelector('[data-slot="tool-fallback-attribution"]'),
    ).toBeNull();
  });

  it("renders nothing for a digigraph-clipped payload (#4131)", () => {
    const { container } = render(
      <ToolFallbackAttribution
        result={{
          result: {
            truncated: true,
            preview: '{"data":{"attribution":"Sourced fr… [truncated]',
          },
        }}
      />,
    );
    expect(
      container.querySelector('[data-slot="tool-fallback-attribution"]'),
    ).toBeNull();
  });

  it("reads a JSON-string result envelope", () => {
    render(
      <ToolFallbackAttribution
        result={{
          result: JSON.stringify({
            attribution: "Sourced from Gloomberb",
            delay_notice: "Data delayed up to 15 minutes",
            source_url: "https://term.gloom.sh/?ticker=BTC-USD",
          }),
        }}
      />,
    );
    const link = screen.getByRole("link", { name: /Open in Gloomberb/ });
    expect(link.getAttribute("href")).toBe(
      "https://term.gloom.sh/?ticker=BTC-USD",
    );
  });
});
