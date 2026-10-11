// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DevkitEditors } from "./devkit-editors";
import { createDraft, type TextEdit } from "./draft";
import type { DigichatDeployment } from "@/lib/deploy-config/schema";

function renderEditors() {
  const text = ["deployment:", "  slug: probe", "  backend:", "    type: digigraph"].join("\n");
  const draft = createDraft({
    entryId: "probe",
    scope: ["deployment"],
    savedText: text,
    parsed: {
      slug: "probe",
      backend: { type: "digigraph" },
      models: {},
      gate: {},
    } as unknown as DigichatDeployment,
  });
  const commit = vi.fn((edit: TextEdit) => edit.applied);
  render(<DevkitEditors draft={draft} commit={commit} />);
}

describe("editor group tabs", () => {
  it("renders one tab per group with Basics selected and expanded", () => {
    renderEditors();
    expect(screen.getByRole("group", { name: /editor groups/i })).not.toBeNull();
    // Exactly one control per group name — no accordion triggers doubling
    // the nav labels.
    for (const name of ["Basics", "Appearance", "Advanced"]) {
      expect(screen.getAllByRole("button", { name })).toHaveLength(1);
    }
    expect(screen.getByRole("button", { name: "Basics" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(screen.getByText("Identity")).not.toBeNull();
    expect(screen.queryByText("MCP servers")).toBeNull();
  });

  it("clicking a tab swaps the visible group", async () => {
    const user = userEvent.setup();
    renderEditors();
    await user.click(screen.getByRole("button", { name: "Advanced" }));
    expect(screen.getByText("MCP servers")).not.toBeNull();
    expect(screen.queryByText("Identity")).toBeNull();
    expect(screen.getByRole("button", { name: "Advanced" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(screen.getByRole("button", { name: "Basics" }).getAttribute("aria-pressed")).toBe(
      "false",
    );
  });

  it("clicking Appearance shows the Appearance section", async () => {
    const user = userEvent.setup();
    renderEditors();
    await user.click(screen.getByRole("button", { name: "Appearance" }));
    expect(screen.getByRole("combobox", { name: /skin/i })).not.toBeNull();
    expect(screen.queryByText("Identity")).toBeNull();
  });
});
