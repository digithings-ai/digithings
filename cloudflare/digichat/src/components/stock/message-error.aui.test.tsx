// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// #3910: a failed turn has to render through the message error UI — the copy
// plus a reachable retry affordance — instead of a success-looking text bubble.
// The primitives are stubbed so the test exercises this component's mapping,
// not assistant-ui internals.
const auiState = vi.hoisted(() => ({ errorText: "" }));

vi.mock("@assistant-ui/react", () => ({
  useAuiState: <T,>(selector: (s: unknown) => T) =>
    selector({
      message: {
        status: {
          type: "incomplete",
          reason: "error",
          error: auiState.errorText,
        },
      },
    }),
  MessagePrimitive: {
    Error: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  },
  ErrorPrimitive: {
    Root: ({ children, ...rest }: React.ComponentProps<"div">) => (
      <div {...rest}>{children}</div>
    ),
    Message: ({ children, ...rest }: React.ComponentProps<"p">) => (
      <p {...rest}>{children}</p>
    ),
  },
  ActionBarPrimitive: {
    // Real primitive is `asChild` — it clones its child and attaches the reload
    // handler, so the mock renders the child directly.
    Reload: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  },
}));

import { MessageError } from "./message-error.aui";

describe("MessageError", () => {
  it("renders upstream-failure copy with a reachable retry affordance", () => {
    auiState.errorText =
      "The assistant is unavailable right now. Please try again shortly.";
    render(<MessageError />);
    expect(screen.getByText(/assistant is unavailable/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
  });

  it("renders BYOK remediation copy for a model-remediable code", () => {
    auiState.errorText = JSON.stringify({ error: "byok_model_required" });
    render(<MessageError />);
    expect(screen.getByText(/needs a model/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
  });
});
