"use client"

import * as React from "react"
import { cn } from "../lib/utils"

type TableProps = React.ComponentProps<"table"> & {
  /** `compact` halves the header/cell padding for dense ledgers. */
  density?: "default" | "compact"
}

function Table({ className, density = "default", ...props }: TableProps) {
  return (
    <div
      data-slot="table-container"
      className="relative w-full overflow-x-auto"
    >
      <table
        data-slot="table"
        data-density={density}
        className={cn(
          "w-full caption-bottom text-xs",
          density === "compact" &&
            "[&_[data-slot=table-head]]:h-8 [&_[data-slot=table-cell]]:py-1 [&_[data-slot=table-row-header]]:py-1",
          className
        )}
        {...props}
      />
    </div>
  )
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn("[&_tr]:border-b [&_tr]:border-border", className)}
      {...props}
    />
  )
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  )
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t border-border bg-muted/50 font-medium [&>tr]:last:border-b-0",
        className
      )}
      {...props}
    />
  )
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "border-b border-border transition-colors hover:bg-muted/50 has-aria-expanded:bg-muted/50 data-[state=selected]:bg-muted",
        className
      )}
      {...props}
    />
  )
}

type TableHeadProps = React.ComponentProps<"th"> & {
  /** Right-aligns the cell and turns on tabular figures (ledger numerals). */
  numeric?: boolean
}

function TableHead({ className, numeric = false, ...props }: TableHeadProps) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "h-10 px-2 text-start align-middle font-medium whitespace-nowrap text-foreground [&:has([role=checkbox])]:pe-0",
        numeric && "text-end tabular-nums",
        className
      )}
      {...props}
    />
  )
}

type TableDataCellProps = React.ComponentProps<"td"> & {
  /** Right-aligns the cell and turns on tabular figures (ledger numerals). */
  numeric?: boolean
}

function TableCell({
  className,
  numeric = false,
  ...props
}: TableDataCellProps) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "p-2 align-middle whitespace-nowrap [&:has([role=checkbox])]:pe-0",
        numeric && "text-end tabular-nums",
        className
      )}
      {...props}
    />
  )
}

/**
 * Row-header cell — the `<th scope="row">` that names a body row (a blotter
 * symbol, a metric label). Cell-shaped (left, body padding) so it sits level
 * with `TableCell`, unlike the column-oriented `TableHead`.
 */
function TableRowHeader({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-row-header"
      scope="row"
      className={cn(
        "p-2 text-start align-middle font-medium whitespace-nowrap text-foreground [&:has([role=checkbox])]:pe-0",
        className
      )}
      {...props}
    />
  )
}

function TableCaption({
  className,
  ...props
}: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-4 text-xs text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableRowHeader,
  TableCaption,
}
