// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DataTable, columnRoles, type DataTableColumn } from "./DataTable";

type Row = { ticker: string; weight: number | null; thesis: string };

const ROWS: Row[] = [
  { ticker: "UUP", weight: 29.97, thesis: "Dollar strength" },
  { ticker: "DBO", weight: -4.72, thesis: "Supply cut" },
  { ticker: "XLV", weight: 12.5, thesis: "Defensive sleeve" },
  { ticker: "GLD", weight: 8.1, thesis: "Hedge" },
  { ticker: "TLT", weight: -1.2, thesis: "Duration" },
];

const COLS: DataTableColumn<Row>[] = [
  {
    key: "ticker",
    label: "ticker",
    role: "key",
    cell: (r) => r.ticker,
    sort: true,
    text: (r) => r.ticker,
  },
  {
    key: "weight",
    label: "weight",
    role: "num",
    cell: (r) => (r.weight == null ? "—" : `${r.weight}%`),
    sort: (r) => r.weight,
    text: (r) => String(r.weight),
  },
  { key: "thesis", label: "thesis", role: "text", cell: (r) => r.thesis, wrap: true },
];

const base = {
  cols: COLS,
  rowKey: (r: Row) => r.ticker,
  label: "holdings",
};

/** Body rows only — the header row is the first `row` in the table. */
const bodyRows = () => screen.getAllByRole("row").slice(1);
const column = (index: number) =>
  bodyRows().map((row) => within(row).getAllByRole("cell")[index].textContent);

afterEach(cleanup);

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
    const roles = columnRoles(
      [],
      [
        ["NAV", "$1,234.56", "+12 bp", "1.8x", "€2.1k"],
        ["Cash", "$98.00", "-3 bp", "0.4x", "€0.3k"],
      ],
    );
    expect(roles).toEqual(["key", "num", "num", "num", "num"]);
  });

  it("keeps a lone column as text and an all-empty column as text", () => {
    expect(columnRoles([], [["Only a sentence row."]])).toEqual(["text"]);
    expect(
      columnRoles(
        [],
        [
          ["a", "—"],
          ["b", ""],
        ],
      ),
    ).toEqual(["key", "text"]);
  });

  it("treats a mixed column as text", () => {
    expect(
      columnRoles(
        [],
        [
          ["a", "12.1"],
          ["b", "rolled"],
        ],
      ),
    ).toEqual(["key", "text"]);
  });
});

describe("DataTable", () => {
  it("renders a labelled, keyboard-scrollable region with a sticky header", () => {
    render(<DataTable {...base} rows={ROWS} />);
    const region = screen.getByRole("region", { name: "holdings table" });
    expect(region.getAttribute("tabindex")).toBe("0");
    expect(region.className).toContain("overflow-x-auto");
    expect(region.className).toContain("border-hair");
    for (const head of screen.getAllByRole("columnheader")) {
      expect(head.className).toContain("sticky");
      expect(head.className).toContain("border-hair-2");
    }
  });

  it("sorts on a real button and reports aria-sort, asc then desc then off", async () => {
    const user = userEvent.setup();
    render(<DataTable {...base} rows={ROWS} />);
    const header = screen.getByRole("columnheader", { name: /ticker/ });
    const button = screen.getByRole("button", { name: /ticker/ });
    expect(header.getAttribute("aria-sort")).toBe("none");

    await user.click(button);
    expect(header.getAttribute("aria-sort")).toBe("ascending");
    expect(column(0)).toEqual(["DBO", "GLD", "TLT", "UUP", "XLV"]);

    await user.click(button);
    expect(header.getAttribute("aria-sort")).toBe("descending");
    expect(column(0)).toEqual(["XLV", "UUP", "TLT", "GLD", "DBO"]);

    await user.click(button);
    expect(header.getAttribute("aria-sort")).toBe("none");
    expect(column(0)).toEqual(["UUP", "DBO", "XLV", "GLD", "TLT"]);
  });

  it("reaches the sort control by keyboard", async () => {
    const user = userEvent.setup();
    render(<DataTable {...base} rows={ROWS} />);
    const button = screen.getByRole("button", { name: /weight/ });
    button.focus();
    expect(document.activeElement).toBe(button);
    await user.keyboard("{Enter}");
    expect(screen.getByRole("columnheader", { name: /weight/ }).getAttribute("aria-sort")).toBe(
      "ascending",
    );
  });

  it("sorts nulls last in both directions and keeps total rows pinned below", async () => {
    const user = userEvent.setup();
    const rows: Row[] = [...ROWS, { ticker: "CASH", weight: null, thesis: "Unallocated" }];
    render(
      <DataTable
        {...base}
        rows={rows}
        variant={(r) => (r.ticker === "CASH" ? "total" : undefined)}
      />,
    );
    const button = screen.getByRole("button", { name: /weight/ });
    await user.click(button);
    expect(column(0).at(-1)).toBe("CASH");
    await user.click(button);
    expect(column(0).at(-1)).toBe("CASH");
  });

  it("filters across columns and reports how many rows survive", async () => {
    const user = userEvent.setup();
    render(<DataTable {...base} rows={ROWS} filter />);
    const box = screen.getByRole("searchbox", { name: "Filter holdings" });
    await user.type(box, "defensive");
    expect(bodyRows()).toHaveLength(1);
    expect(screen.getByText("1/5")).toBeTruthy();

    await user.clear(box);
    await user.type(box, "zzz");
    expect(screen.getByText("no match")).toBeTruthy();
  });

  it("pages through the rows and disables the ends", async () => {
    const user = userEvent.setup();
    render(<DataTable {...base} rows={ROWS} pageSize={2} />);
    expect(bodyRows()).toHaveLength(2);
    expect(screen.getByText("1 / 3")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Previous page" }).hasAttribute("disabled")).toBe(
      true,
    );

    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(column(0)).toEqual(["XLV", "GLD"]);
    expect(screen.getByText("2 / 3")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByRole("button", { name: "Next page" }).hasAttribute("disabled")).toBe(true);
  });

  it("right-aligns and tabulates numeric cells by role", () => {
    render(<DataTable {...base} rows={ROWS} />);
    const head = screen.getByRole("columnheader", { name: /weight/ });
    expect(head.getAttribute("data-col")).toBe("num");
    expect(head.className).toContain("text-right");

    const cells = within(bodyRows()[0]).getAllByRole("cell");
    expect(cells[1].getAttribute("data-col")).toBe("num");
    expect(cells[1].className).toContain("text-right");
    expect(cells[1].className).toContain("[font-variant-numeric:tabular-nums]");
    expect(cells[0].getAttribute("data-col")).toBe("key");
    expect(cells[2].getAttribute("data-col")).toBe("text");
  });

  it("wears the money colours on a toned cell", () => {
    render(
      <DataTable
        {...base}
        rows={ROWS}
        cols={COLS.map((c) =>
          c.key === "weight"
            ? { ...c, tone: (r: Row) => ((r.weight ?? 0) >= 0 ? "pos" : "neg") }
            : c,
        )}
      />,
    );
    const cells = within(bodyRows()[0]).getAllByRole("cell");
    expect(cells[1].className).toContain("text-up");
    const second = within(bodyRows()[1]).getAllByRole("cell");
    expect(second[1].className).toContain("text-down");
  });

  it("activates a row by click, Enter and Space", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    render(<DataTable {...base} rows={ROWS} onRowClick={onRowClick} />);
    const row = bodyRows()[0];
    expect(row.getAttribute("tabindex")).toBe("0");

    await user.click(row);
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0], 0);

    row.focus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");
    expect(onRowClick).toHaveBeenCalledTimes(3);
  });

  it("shows the empty line when the payload has no rows", () => {
    render(<DataTable {...base} rows={[]} empty="no holdings yet" />);
    expect(screen.getByText("no holdings yet")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
