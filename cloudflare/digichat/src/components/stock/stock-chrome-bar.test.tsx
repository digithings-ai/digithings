// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StockChromeBar } from "./stock-chrome-bar";

describe("StockChromeBar", () => {
  it("changes language", async () => {
    const user = userEvent.setup();
    const onLanguageChange = vi.fn();
    render(
      <StockChromeBar language="en" onLanguageChange={onLanguageChange} />,
    );
    await user.selectOptions(screen.getByLabelText("Reply language"), "de");
    expect(onLanguageChange).toHaveBeenCalledWith("de");
  });

  it("opens help and starts a new conversation", async () => {
    const user = userEvent.setup();
    const onNewThread = vi.fn();
    render(<StockChromeBar onNewThread={onNewThread} />);
    await user.click(screen.getByRole("button", { name: "Help" }));
    expect(screen.getByRole("dialog", { name: "Help" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New conversation" }));
    expect(onNewThread).toHaveBeenCalledOnce();
  });
});
