// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// NOTE: TextRow/BoolRow must be exported from devkit-editors.tsx for this
// test (export the row primitives; the default export surface is unchanged).
import { BoolRow, TextRow } from "./devkit-editors";

describe("TextRow (kit)", () => {
  it("commits a changed value and returns true", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn().mockReturnValue(true);
    render(<TextRow label="slug" value="old" onCommit={onCommit} />);
    await user.click(screen.getByLabelText(/slug/i));
    await user.clear(screen.getByLabelText(/slug/i));
    await user.type(screen.getByLabelText(/slug/i), "new");
    await user.tab();
    expect(onCommit).toHaveBeenCalledWith("new");
  });

  it("reverts its display when the commit is refused", async () => {
    const user = userEvent.setup();
    render(<TextRow label="slug" value="old" onCommit={() => false} />);
    const input = screen.getByLabelText(/slug/i) as HTMLInputElement;
    await user.click(input);
    await user.clear(input);
    await user.type(input, "rejected");
    await user.tab();
    expect(input.value).toBe("old");
  });
});

describe("BoolRow (kit Switch)", () => {
  it("commits the toggled value", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn().mockReturnValue(true);
    render(<BoolRow label="attachments" checked={false} onCommit={onCommit} />);
    await user.click(screen.getByRole("switch", { name: /attachments/i }));
    expect(onCommit).toHaveBeenCalledWith(true);
  });

  it("reverts when the commit is refused", async () => {
    const user = userEvent.setup();
    render(<BoolRow label="attachments" checked={false} onCommit={() => false} />);
    const sw = screen.getByRole("switch", { name: /attachments/i });
    await user.click(sw);
    expect(sw.getAttribute("aria-checked")).toBe("false");
  });
});
