// @vitest-environment happy-dom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LanguageSelect } from "@/components/language-select";

describe("LanguageSelect", () => {
  it("renders the currently selected language's label as the trigger text", () => {
    render(<LanguageSelect value="de" onChange={() => {}} />);
    expect(screen.getByRole("button", { name: /german/i })).toBeInTheDocument();
  });

  it("lists all five curated languages when opened", async () => {
    const user = userEvent.setup();
    render(<LanguageSelect value="en" onChange={() => {}} />);
    await user.click(screen.getByRole("button", { name: /english/i }));
    for (const label of ["English", "German", "Italian", "Spanish", "French"]) {
      expect(screen.getByRole("menuitem", { name: label })).toBeInTheDocument();
    }
  });

  it("calls onChange with the picked language's code", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<LanguageSelect value="en" onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /english/i }));
    await user.click(screen.getByRole("menuitem", { name: "German" }));
    expect(onChange).toHaveBeenCalledWith("de");
  });
});
