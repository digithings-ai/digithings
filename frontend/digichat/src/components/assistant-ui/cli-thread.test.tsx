// @vitest-environment happy-dom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ComponentProps, ReactNode } from "react";
import type { UIMessage } from "ai";

const sendMessage = vi.fn();
let mockMessages: UIMessage[] = [];
let mockStatus = "ready";

vi.mock("@assistant-ui/ai-sdk", () => ({
  useAISDKChat: () => ({
    messages: mockMessages,
    status: mockStatus,
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
    Messages: ({
      children,
    }: {
      children: (args: { message: { id: string; role: string } }) => ReactNode;
    }) => <>{mockMessages.map((m) => children({ message: { id: m.id, role: m.role } }))}</>,
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
  ChatThinking: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  ChatToolCall: ({ name, children }: { name: string; children?: ReactNode }) => (
    <div>
      {name}
      {children}
    </div>
  ),
}));

vi.mock("@/components/echarts-card", () => ({
  EChartsCard: () => null,
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...rest }: ComponentProps<"button">) => (
    <button type="button" {...rest}>
      {children}
    </button>
  ),
}));

import { CliThread } from "./cli-thread";

describe("CliThread", () => {
  beforeEach(() => {
    mockMessages = [];
    mockStatus = "ready";
    sendMessage.mockReset();
  });

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

  it("shows regen/edit when turn mutation is allowed", async () => {
    mockMessages = [
      { id: "u1", role: "user", parts: [{ type: "text", text: "hi" }] } as UIMessage,
      { id: "a1", role: "assistant", parts: [{ type: "text", text: "hello" }] } as UIMessage,
    ];
    const onRegenerate = vi.fn();
    const onEditLastUser = vi.fn();
    const user = userEvent.setup();
    render(
      <CliThread allowTurnMutation onRegenerate={onRegenerate} onEditLastUser={onEditLastUser} />,
    );
    expect(screen.getByText("hello")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "regen" }));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "edit" }));
    expect(screen.getByLabelText("Edit last message")).toBeTruthy();
    await user.clear(screen.getByLabelText("Edit last message"));
    await user.type(screen.getByLabelText("Edit last message"), "edited{Enter}");
    expect(onEditLastUser).toHaveBeenCalledWith("edited");
  });

  it("hides regen when allowTurnMutation is false", () => {
    mockMessages = [
      { id: "u1", role: "user", parts: [{ type: "text", text: "hi" }] } as UIMessage,
      { id: "a1", role: "assistant", parts: [{ type: "text", text: "hello" }] } as UIMessage,
    ];
    render(<CliThread />);
    expect(screen.queryByRole("button", { name: "regen" })).toBeNull();
    expect(screen.queryByRole("button", { name: "edit" })).toBeNull();
  });
});
