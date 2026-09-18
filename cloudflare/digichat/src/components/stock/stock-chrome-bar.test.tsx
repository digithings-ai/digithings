// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StockChromeBar } from "./stock-chrome-bar";

describe("StockChromeBar", () => {
  // Wave 4 (#4306): the language/model pickers moved from a native <select>
  // to the kit Select (a Base UI listbox). The interaction therefore opens the
  // trigger and clicks the option instead of selectOptions() on a <select>;
  // the assertion (code "de" reaches onLanguageChange) is unchanged.
  it("changes language", async () => {
    const user = userEvent.setup();
    const onLanguageChange = vi.fn();
    render(
      <StockChromeBar language="en" onLanguageChange={onLanguageChange} />,
    );
    await user.click(screen.getByRole("combobox", { name: "Reply language" }));
    await user.click(await screen.findByRole("option", { name: "German" }));
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
