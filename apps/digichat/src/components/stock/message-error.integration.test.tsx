// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// WS4 inversion follow-up (review finding): the package banner cannot import
// the app's `@/lib/embed-chat-error` mapping, so the package suite pins the
// injection paths with stub parsers. This suite re-pins the real wiring on
// the app side, where both are importable — package MessageError + real app
// parsers must render the product BYOK copy.
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
      Reload: ({ children }: { children: React.ReactNode }) =>
        cloneElement(
          children as React.ReactElement<{ onClick?: () => void }>,
          { onClick: retry.onClick },
        ),
    },
  };
});

import { MessageError, SkinRuntimeProvider } from "@digithings/ui/chat/stock";
import {
  BYOK_MODEL_REMEDIABLE_MESSAGE,
  formatEmbedChatError,
  parseEmbedChatError,
} from "@/lib/embed-chat-error";

beforeEach(() => {
  retry.onClick.mockClear();
});

afterEach(() => {
  cleanup();
});

describe("MessageError with the product parsers", () => {
  it("renders the BYOK copy with parsers passed as props", async () => {
    auiState.errorText = JSON.stringify({ error: "byok_model_required" });
    const user = userEvent.setup();
    render(
      <MessageError
        parseError={parseEmbedChatError}
        formatError={formatEmbedChatError}
      />,
    );
    expect(screen.getByText(BYOK_MODEL_REMEDIABLE_MESSAGE)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(retry.onClick).toHaveBeenCalledOnce();
  });

  it("renders the BYOK copy with parsers from SkinRuntimeProvider", async () => {
    auiState.errorText = JSON.stringify({ error: "byok_model_required" });
    const user = userEvent.setup();
    render(
      <SkinRuntimeProvider
        value={{
          errorParsers: {
            parseError: parseEmbedChatError,
            formatError: formatEmbedChatError,
          },
        }}
      >
        <MessageError />
      </SkinRuntimeProvider>,
    );
    expect(screen.getByText(BYOK_MODEL_REMEDIABLE_MESSAGE)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(retry.onClick).toHaveBeenCalledOnce();
  });
});
