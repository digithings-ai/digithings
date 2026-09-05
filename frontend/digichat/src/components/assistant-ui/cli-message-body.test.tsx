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

vi.mock("@digithings/digichat-ui", () => ({
  ChatActivities: () => null,
}));

vi.mock("@/components/echarts-card", () => ({
  EChartsCard: () => <div data-testid="chart" />,
}));

import { CliMessageBody } from "./cli-message-body";

describe("CliMessageBody", () => {
  it("renders user text", () => {
    const message = {
      id: "u1",
      role: "user",
      parts: [{ type: "text", text: "hello" }],
    } as UIMessage;
    render(<CliMessageBody message={message} />);
    expect(screen.getByText("hello")).toBeTruthy();
  });

  it("renders reasoning parts", () => {
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
});
