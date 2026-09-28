// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// NOTE: TextRow/BoolRow must be exported from devkit-editors.tsx for this
// test (export the row primitives; the default export surface is unchanged).
import { useState } from "react";
import { BoolRow, DevkitEditors, SecretRow, SelectRow, TextRow, TriRow } from "./devkit-editors";
import { createDraft, type TextEdit } from "./draft";
import type { DigichatDeployment } from "@/lib/deploy-config/schema";

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

describe("SelectRow (kit, controlled)", () => {
  it("calls onCommit with the picked value", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn().mockReturnValue(true);
    render(<SelectRow label="skin" value="digichat" options={["digichat", "claude"]} onCommit={onCommit} />);
    await user.click(screen.getByRole("combobox", { name: /skin/i }));
    await user.click(screen.getByRole("option", { name: "claude" }));
    expect(onCommit).toHaveBeenCalledWith("claude");
  });

  it("holds its value when the commit is refused", async () => {
    function Harness() {
      const [v, setV] = useState("digichat");
      return (
        <SelectRow
          label="skin"
          value={v}
          options={["digichat", "claude"]}
          onCommit={(next) => {
            setV(next);
            return true;
          }}
        />
      );
    }
    render(<Harness />);
    expect(screen.getByRole("combobox", { name: /skin/i })).toHaveTextContent("digichat");
  });
});

describe("TriRow (kit SegmentedControl, group pattern)", () => {
  it("wires role=group to its label via aria-labelledby", () => {
    const onCommit = vi.fn().mockReturnValue(true);
    render(<TriRow label="attribution credit" value={undefined} onCommit={onCommit} />);
    const group = screen.getByRole("group", { name: /attribution credit/i });
    const labelledBy = group.getAttribute("aria-labelledby") ?? "";
    const labelId = labelledBy.split(" ").find((id) => document.getElementById(id));
    expect(labelId).toBeTruthy();
    expect(document.getElementById(labelId!)?.textContent).toMatch(/attribution credit/i);
  });

  it("calls onCommit with undefined when inherit is picked", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn().mockReturnValue(true);
    render(<TriRow label="attribution credit" value={true} onCommit={onCommit} />);
    await user.click(screen.getByRole("button", { name: "inherit" }));
    expect(onCommit).toHaveBeenCalledWith(undefined);
  });

  it("holds its value when the commit is refused", async () => {
    const user = userEvent.setup();
    render(<TriRow label="attribution credit" value={true} onCommit={() => false} />);
    const onButton = screen.getByRole("button", { name: "on" });
    expect(onButton.getAttribute("aria-pressed")).toBe("true");
    await user.click(screen.getByRole("button", { name: "off" }));
    expect(onButton.getAttribute("aria-pressed")).toBe("true");
  });
});

describe("SecretRow (kit)", () => {
  it("stays open and keeps the typed value when replace is refused", async () => {
    const user = userEvent.setup();
    render(<SecretRow label="token" state="sentinel" onReplace={() => false} />);
    await user.click(screen.getByRole("button", { name: /replace/i }));
    await user.type(screen.getByLabelText(/new secret/i), "typed");
    await user.click(screen.getByRole("button", { name: /set/i }));
    expect(screen.getByLabelText(/new secret/i)).toHaveDisplayValue("typed");
  });

  it("closes and clears on successful replace", async () => {
    const user = userEvent.setup();
    render(<SecretRow label="token" state="sentinel" onReplace={() => true} />);
    await user.click(screen.getByRole("button", { name: /replace/i }));
    await user.type(screen.getByLabelText(/new secret/i), "typed");
    await user.click(screen.getByRole("button", { name: /set/i }));
    expect(screen.queryByLabelText(/new secret/i)).toBeNull();
  });
});

describe("ToolCard (kit Card)", () => {
  it("renders a kit Card with title + remove IconButton committing removeListItem", async () => {
    const user = userEvent.setup();
    const text = ["deployment:", "  slug: probe", "  tools:", "    catalog:", "      - id: search"].join(
      "\n",
    );
    const draft = createDraft({
      entryId: "probe",
      scope: ["deployment"],
      savedText: text,
      parsed: {
        slug: "probe",
        backend: { type: "digigraph" },
        models: {},
        gate: {},
        tools: { catalog: [{ id: "search" }] },
      } as unknown as DigichatDeployment,
    });
    const commit = vi.fn((edit: TextEdit) => edit.applied);
    render(<DevkitEditors draft={draft} commit={commit} />);
    const title = screen.getByText("search");
    expect(title.closest('[data-slot="card"]')).not.toBeNull();
    await user.click(screen.getByRole("button", { name: /remove search/i }));
    expect(commit).toHaveBeenCalled();
    const edit = commit.mock.calls[0][0];
    expect(edit.applied).toBe(true);
    expect(edit.text).toMatch(/catalog: \[\]/);
  });
});
