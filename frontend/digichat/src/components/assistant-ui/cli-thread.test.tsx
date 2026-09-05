// @vitest-environment happy-dom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ComponentProps, ReactNode } from "react";

const sendMessage = vi.fn();

vi.mock("@assistant-ui/ai-sdk", () => ({
  useAISDKChat: () => ({
    messages: [],
    status: "ready",
    sendMessage,
    stop: vi.fn(),
    setMessages: vi.fn(),
  }),
}));

vi.mock("@assistant-ui/react", () => ({
  ThreadPrimitive: {
    Root: ({ children, className, ...rest }: { children?: ReactNode; className?: string }) => (
      <div className={className} {...rest}>
        {children}
      </div>
    ),
    Viewport: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    Empty: ({ children }: { children?: ReactNode }) => <>{children}</>,
    Messages: () => null,
  },
  ComposerPrimitive: {
    Root: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    Input: (props: ComponentProps<"textarea">) => <textarea {...props} />,
  },
  MessagePrimitive: { Root: "div", Parts: () => null },
  ActionBarPrimitive: { Root: "div", Copy: "button" },
}));

vi.mock("@digithings/web", () => ({
  ChatMarkdown: ({ source }: { source: string }) => <div>{source}</div>,
}));

import { CliThread } from "./cli-thread";

describe("CliThread", () => {
  it("renders the empty hint and CLI composer", () => {
    render(<CliThread placeholder="ask digichat…" />);
    expect(screen.getByText(/digichat ready/)).toBeTruthy();
    expect(screen.getByPlaceholderText("ask digichat…")).toBeTruthy();
  });

  it("hides the empty hint when emptyHint is null", () => {
    render(<CliThread emptyHint={null} />);
    expect(screen.queryByText(/digichat ready/)).toBeNull();
  });

  it("shows error text and an optional action", () => {
    render(
      <CliThread
        errorText="quota exceeded"
        errorAction={<button type="button">Add your API key (/byok)</button>}
      />,
    );
    expect(screen.getByText("quota exceeded")).toBeTruthy();
    expect(screen.getByText("Add your API key (/byok)")).toBeTruthy();
  });

  it("lists slash commands when the composer starts with /", async () => {
    const user = userEvent.setup();
    render(<CliThread slashVisibility={{ webSearch: true, byok: true }} />);
    await user.type(screen.getByPlaceholderText("ask digichat"), "/");
    expect(screen.getByLabelText("Slash commands")).toBeTruthy();
    expect(screen.getByText("Search the knowledge base")).toBeTruthy();
  });

  it("lets onSendRequest swallow a plain question", async () => {
    const onSendRequest = vi.fn(() => true);
    const user = userEvent.setup();
    render(<CliThread onSendRequest={onSendRequest} />);
    await user.type(screen.getByPlaceholderText("ask digichat"), "hello{Enter}");
    expect(onSendRequest).toHaveBeenCalledWith("hello", undefined);
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("passes X-Digi-Force-Tool via onSendRequest for /search", async () => {
    const onSendRequest = vi.fn(() => true);
    const user = userEvent.setup();
    render(<CliThread onSendRequest={onSendRequest} />);
    await user.type(screen.getByPlaceholderText("ask digichat"), "/search jwt{Enter}");
    expect(onSendRequest).toHaveBeenCalledWith("jwt", { forceTool: "digisearch" });
  });
});
