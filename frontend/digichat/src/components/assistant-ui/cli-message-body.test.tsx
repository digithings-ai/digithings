// @vitest-environment happy-dom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { UIMessage } from "ai";

vi.mock("@digithings/web", () => ({
  ChatMarkdown: ({ source }: { source: string }) => <div data-testid="md">{source}</div>,
  ChatThinking: ({ children, label }: { children?: unknown; label?: string }) => (
    <div data-testid="thinking">
      {label}
      {children}
    </div>
  ),
  ChatToolCall: ({ name, children }: { name: string; children?: unknown }) => (
    <div data-testid="tool">
      {name}
      {children}
    </div>
  ),
}));

import { CliMessageBody, LegacyActivityHydrate, needsLegacyActivityHydrate } from "./cli-message-body";

describe("CliMessageBody / legacy hydrate", () => {
  it("renders user text", () => {
    const message = {
      id: "u1",
      role: "user",
      parts: [{ type: "text", text: "hello" }],
    } as UIMessage;
    render(<CliMessageBody message={message} />);
    expect(screen.getByText("hello")).toBeTruthy();
  });

  it("renders reasoning parts without ChatActivities", () => {
    const message = {
      id: "a1",
      role: "assistant",
      parts: [
        { type: "reasoning", text: "pondering", state: "done" },
        { type: "text", text: "answer" },
      ],
    } as UIMessage;
    render(<CliMessageBody message={message} />);
    expect(screen.getByTestId("thinking").textContent).toContain("pondering");
    expect(screen.getByText("answer")).toBeTruthy();
  });

  it("hydrates branded activity only when no standard parts exist", () => {
    const branded = {
      id: "a2",
      role: "assistant",
      parts: [
        {
          type: "data-digichatActivity",
          id: "x",
          data: {
            operation: "execute_tool",
            status: "started",
            label: "Searching…",
            toolName: "digisearch",
            query: "jwt",
          },
        },
      ],
    } as UIMessage;
    expect(needsLegacyActivityHydrate(branded)).toBe(true);
    render(<LegacyActivityHydrate message={branded} />);
    expect(screen.getByTestId("tool").textContent).toContain("digisearch");

    const mixed = {
      id: "a3",
      role: "assistant",
      parts: [
        { type: "reasoning", text: "x", state: "done" },
        {
          type: "data-digichatActivity",
          id: "x",
          data: {
            operation: "execute_tool",
            status: "started",
            label: "Searching…",
            toolName: "digisearch",
          },
        },
      ],
    } as UIMessage;
    expect(needsLegacyActivityHydrate(mixed)).toBe(false);
  });
});
