// @vitest-environment happy-dom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...rest }: ComponentProps<"button">) => (
    <button type="button" {...rest}>
      {children}
    </button>
  ),
}));

import { ToolFallback } from "./tool-fallback";

describe("ToolFallback", () => {
  it("shows assistant-ui used-tool chrome and expands args", async () => {
    const user = userEvent.setup();
    render(
      <ToolFallback
        type="tool-call"
        toolCallId="t1"
        toolName="digisearch"
        args={{ query: "jwt" }}
        argsText='{"query":"jwt"}'
        result={{ hitCount: 2 }}
        isError={false}
        status={{ type: "complete" }}
        addResult={() => undefined}
        resume={() => undefined}
        respondToApproval={async () => undefined}
      />,
    );
    expect(screen.getByText(/Used tool:/)).toBeTruthy();
    expect(screen.getByText("digisearch")).toBeTruthy();
    expect(screen.queryByText(/"query":"jwt"/)).toBeNull();
    await user.click(screen.getByRole("button"));
    expect(screen.getByText(/"query":"jwt"/)).toBeTruthy();
    expect(screen.getByText("Result")).toBeTruthy();
  });

  it("renders the raw backend tool id with underscores", () => {
    render(
      <ToolFallback
        type="tool-call"
        toolCallId="t2"
        toolName="digivault_get_note"
        args={{ vault_paths: ["a.md"] }}
        argsText='{"vault_paths":["a.md"]}'
        result={{ hitCount: 1 }}
        isError={false}
        status={{ type: "complete" }}
        addResult={() => undefined}
        resume={() => undefined}
        respondToApproval={async () => undefined}
      />,
    );
    expect(screen.getByText("digivault_get_note")).toBeTruthy();
    expect(screen.queryByText("digivault get note")).toBeNull();
  });

  it("renders the digisearch row with the exact backend id", () => {
    render(
      <ToolFallback
        type="tool-call"
        toolCallId="t3"
        toolName="digisearch"
        args={{ query: "jwt", mode: "keyword" }}
        argsText='{"query":"jwt","mode":"keyword"}'
        result={{ hitCount: 0 }}
        isError={false}
        status={{ type: "complete" }}
        addResult={() => undefined}
        resume={() => undefined}
        respondToApproval={async () => undefined}
      />,
    );
    expect(screen.getByText("digisearch")).toBeTruthy();
  });
});
