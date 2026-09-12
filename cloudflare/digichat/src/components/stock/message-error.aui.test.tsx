// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// #3910: a failed turn has to render through the message error UI — the copy
// plus a reachable retry affordance — instead of a success-looking text bubble.
// The primitives are stubbed so the test exercises this component's mapping,
// not assistant-ui internals.
const auiState = vi.hoisted(() => ({ errorText: "" }));
const retry = vi.hoisted(() => ({ onClick: vi.fn() }));

vi.mock("@assistant-ui/react", async () => {
  const { cloneElement } = await import("react");
  return {
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
      // Real primitive is `asChild` — it clones its child and attaches the
      // reload handler. Emulate that so the test can click through the button.
      Reload: ({ children }: { children: React.ReactNode }) =>
        cloneElement(
          children as React.ReactElement<{ onClick?: () => void }>,
          { onClick: retry.onClick },
        ),
    },
  };
});

import { MessageError } from "./message-error.aui";

beforeEach(() => {
  retry.onClick.mockClear();
});

describe("MessageError", () => {
  it("renders upstream-failure copy with a reachable retry affordance", async () => {
    auiState.errorText =
      "The assistant is unavailable right now. Please try again shortly.";
    const user = userEvent.setup();
    render(<MessageError />);
    expect(screen.getByText(/assistant is unavailable/i)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(retry.onClick).toHaveBeenCalledOnce();
  });

  it("renders BYOK remediation copy for a model-remediable code", async () => {
    auiState.errorText = JSON.stringify({ error: "byok_model_required" });
    const user = userEvent.setup();
    render(<MessageError />);
    expect(screen.getByText(/needs a model/i)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(retry.onClick).toHaveBeenCalledOnce();
  });
});
