/**
 * Table — the plain hairline-ledger primitive. Behavior-free: a thin,
 * accessible shell over the native table elements (no sorting, no virtual
 * rows — those stay in SortableTable / TradeLogTable / PricingMatrix, which
 * own their opinionated grammars). All dress lives in
 * styles/controls-core.css (`.ctl-table*`, import once app-wide); this file
 * carries no Tailwind utilities, so no `@source` line is needed for it.
 *
 * Grammar: mono numerals, one hairline per row, micro-cap header, caption
 * below the table. Numeric columns take `numeric` for right alignment +
 * tabular figures. Wrap wide tables in `.ctl-table-scroll` (overflow-x).
 * `density="compact"` halves the cell padding for dense ledgers.
 */
import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";

import { cx } from "./cx";

export type TableDensity = "default" | "compact";

export function Table({
  density = "default",
  className,
  ...props
}: HTMLAttributes<HTMLTableElement> & { density?: TableDensity }) {
  return (
    <table
      data-slot="table"
      data-density={density}
      className={cx("ctl-table", className)}
      {...props}
    />
  );
}

export function TableHeader({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <thead data-slot="table-header" className={cx("ctl-table-head", className)} {...props} />;
}

export function TableBody({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <tbody data-slot="table-body" className={cx("ctl-table-body", className)} {...props} />;
}

export function TableFooter({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <tfoot data-slot="table-footer" className={cx("ctl-table-foot", className)} {...props} />;
}

export function TableRow({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr data-slot="table-row" className={cx("ctl-table-row", className)} {...props} />;
}

export function TableHead({
  numeric = false,
  className,
  ...props
}: ThHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <th
      data-slot="table-head"
      className={cx("ctl-table-th", numeric && "ctl-table-num", className)}
      {...props}
    />
  );
}

export function TableCell({
  numeric = false,
  className,
  ...props
}: TdHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <td
      data-slot="table-cell"
      className={cx("ctl-table-td", numeric && "ctl-table-num", className)}
      {...props}
    />
  );
}

export function TableCaption({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <caption data-slot="table-caption" className={cx("ctl-table-caption", className)} {...props} />;
}
