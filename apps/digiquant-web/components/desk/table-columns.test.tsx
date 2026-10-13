import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DeskPane } from "./pages/pane";
import { columnRoles } from "./table-columns";

const noop = () => {};

describe("columnRoles", () => {
  it("pins the first column, keeps numbers and dates whole, lets prose wrap", () => {
    const roles = columnRoles(
      ["ticker", "weight", "since", "thesis"],
      [
        ["UUP", "29.97%", "2026-09-28", "Dollar strength into the Fed meeting"],
        ["DBO", "−4.72%", "2026-09-28", "Supply cut, short squeeze risk"],
        ["XLV", "—", "n/a", "Defensive sleeve"],
      ],
    );
    expect(roles).toEqual(["key", "num", "num", "text"]);
  });

  it("reads money, bp, multiples and grouped thousands as numbers", () => {
    const roles = columnRoles([], [
      ["NAV", "$1,234.56", "+12 bp", "1.8x", "€2.1k"],
      ["Cash", "$98.00", "-3 bp", "0.4x", "€0.3k"],
    ]);
    expect(roles).toEqual(["key", "num", "num", "num", "num"]);
  });

  it("keeps a lone column as text and an all-empty column as text", () => {
    expect(columnRoles([], [["Only a sentence row."]])).toEqual(["text"]);
    expect(columnRoles([], [["a", "—"], ["b", ""]])).toEqual(["key", "text"]);
  });

  it("treats a mixed column as text", () => {
    expect(columnRoles([], [["a", "12.1"], ["b", "rolled"]])).toEqual(["key", "text"]);
  });
});

describe("desk pane table on a phone", () => {
  const html = renderToStaticMarkup(
    <DeskPane
      title="Book · allocation"
      route="/portfolio"
      asOf={null}
      blocks={{
        blocks: [
          {
            kind: "table",
            columns: ["ticker", "weight", "thesis"],
            rows: [["UUP", "29.97%", "Dollar strength into the Fed meeting"]],
          },
        ],
      }}
      tone=""
      focused={false}
      onFocus={noop}
      onNext={noop}
    />,
  );

  it("wraps the table in a labelled, keyboard-scrollable region", () => {
    expect(html).toMatch(/<div[^>]*class="desk-table-scroll[^"]*"[^>]*>\s*<table/);
    expect(html).toContain('role="region"');
    expect(html).toContain('aria-label="Book · allocation table"');
    expect(html).toContain('tabindex="0"');
  });

  it("marks each cell with its column role", () => {
    expect(html).toMatch(/<th[^>]*data-col="key"[^>]*>ticker</);
    expect(html).toMatch(/<td[^>]*data-col="num"[^>]*>29\.97%</);
    expect(html).toMatch(/<td[^>]*data-col="text"[^>]*>Dollar strength/);
  });

  it("scrolls sideways instead of crushing or clipping the table", () => {
    const css = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf8");
    const rule = (selector: string) => {
      const start = css.indexOf(`${selector} {`);
      expect(start, selector).toBeGreaterThan(-1);
      return css.slice(start, css.indexOf("}", start));
    };
    expect(rule(".desk-table-scroll")).toMatch(/overflow-x:\s*auto/);
    expect(rule(".desk-pane-table")).toMatch(/width:\s*max-content/);
    expect(rule(".desk-pane-table")).toMatch(/min-width:\s*100%/);
    expect(rule('.desk-pane-table [data-col="key"]')).toMatch(/position:\s*sticky/);
    expect(rule('.desk-pane-table [data-col="num"]')).toMatch(/white-space:\s*nowrap/);
    // The old phone rule squeezed every column into the screen and broke numbers mid-digit.
    expect(css).not.toMatch(/\.desk-pane-table\s*\{[^}]*table-layout:\s*fixed/);
    expect(css).not.toMatch(/\.desk-pane-table td\s*\{[^}]*overflow-wrap:\s*anywhere/);
  });
});
