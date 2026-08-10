/**
 * SSR smoke tests for the CommandPalette shell (#1548): the palette renders
 * its grouped listbox with the correct ARIA contract (dialog + listbox +
 * option children + aria-activedescendant), recomputes items through the
 * `groups` function form, and honors the reference row grammar (livery
 * scope, dot, kbd hint, footer legend).
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CommandPalette, type CommandPaletteGroup } from "./CommandPalette";

const noop = () => {};

const GROUPS: CommandPaletteGroup[] = [
  {
    label: "Actions",
    items: [
      { id: "backtest", label: "Run a backtest", kbd: "B", livery: "digiquant", dot: true },
      { id: "chat", label: "Ask digichat", kbd: "C", dot: true },
    ],
  },
  {
    label: "Navigate",
    items: [{ id: "olympus", label: "Open olympus", description: "atlas + hermes" }],
  },
];

describe("CommandPalette", () => {
  it("renders nothing while closed", () => {
    const html = renderToStaticMarkup(
      <CommandPalette open={false} onClose={noop} groups={GROUPS} portal={false} />
    );
    expect(html).toBe("");
  });

  it("renders the grouped listbox with the ARIA contract", () => {
    const html = renderToStaticMarkup(
      <CommandPalette open onClose={noop} groups={GROUPS} portal={false} footer />
    );
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain('role="listbox"');
    expect(html).toContain("aria-activedescendant");
    expect(html).toContain('role="option"');
    expect(html).toContain('aria-selected="true"'); // first row starts active
    expect(html).toContain("cp-group-label");
    expect(html).toContain('role="group"');
  });

  it("honors the row grammar: livery scope, dot, kbd hint, description", () => {
    const html = renderToStaticMarkup(
      <CommandPalette open onClose={noop} groups={GROUPS} portal={false} footer />
    );
    expect(html).toContain("accent-digiquant");
    expect(html).toContain("cp-dot");
    expect(html).toContain("cp-row-key");
    expect(html).toContain("cp-desc");
    expect(html).toContain("atlas + hermes");
    expect(html).toContain("cp-foot"); // footer legend
    expect(html).toContain("navigate");
  });

  it("recomputes items through the groups function (empty query on open)", () => {
    const html = renderToStaticMarkup(
      <CommandPalette
        open
        onClose={noop}
        groups={(q) => (q === "" ? GROUPS : [])}
        portal={false}
      />
    );
    expect(html).toContain("Run a backtest");
  });

  it("renders the empty state without an active descendant", () => {
    const html = renderToStaticMarkup(
      <CommandPalette open onClose={noop} groups={[]} portal={false} />
    );
    expect(html).toContain("cp-empty");
    expect(html).not.toContain("aria-activedescendant");
    expect(html).not.toContain('role="option"');
  });
});
