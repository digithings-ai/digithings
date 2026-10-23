"use client";

import { DASH, cell } from "digiquant-tui/format";
import type { ReadResult } from "digiquant-tui/read";
import {
  BlockBoundary,
  DataTable,
  KpiGrid,
  StateBlock,
  type DataTableColumn,
  type DataTableRowVariant,
  type KpiCell,
} from "@digithings/ui";
import { isRecord } from "@digithings/ui/lib/record";

const ROUTE = "/ledger/cash";

const ABSENT = "not in payload";
const NO_BALANCE = "no latest balance for every account";

export type CashLedgerBlockProps = {
  /** The desk read for `/ledger/cash`. `undefined` while the first fetch is in flight. */
  read?: ReadResult;
  /** The envelope's `data`, when the read is ok and carried one. */
  data?: unknown;
};

/** One cash movement or one period's closing balance, as the payload carried it. */
type Entry = {
  id: string;
  date: string;
  kind: string;
  account: string | null;
  currency: string | null;
  amount: number | null;
  balance: number | null;
};

/** The latest balance the payload holds for one account/currency pair. */
type Group = {
  key: string;
  account: string | null;
  currency: string | null;
  latest: Entry | null;
};

type BalanceRow = {
  id: string;
  account: string;
  currency: string;
  date: string;
  balance: string;
  total: boolean;
};

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** The account and currency a row names, when it names one. No default, no inferred code. */
function identity(raw: Record<string, unknown>): { account: string | null; currency: string | null } {
  return {
    account: text(raw.account) ?? text(raw.account_id) ?? text(raw.venue),
    currency: text(raw.currency) ?? text(raw.currency_code),
  };
}

function readEntries(raw: unknown): { entries: Entry[]; skipped: number } {
  if (!Array.isArray(raw)) return { entries: [], skipped: 0 };
  const entries: Entry[] = [];
  let skipped = 0;
  for (const [index, item] of raw.entries()) {
    if (!isRecord(item)) {
      skipped += 1;
      continue;
    }
    const date = text(item.date);
    if (!date) {
      skipped += 1;
      continue;
    }
    entries.push({
      id: `${date}-${index}`,
      date,
      kind: text(item.kind) ?? DASH,
      ...identity(item),
      amount: finite(item.amount),
      balance: finite(item.balance),
    });
  }
  return { entries, skipped };
}

/** The latest dated balance in a set. Ties keep the first one the payload listed. */
function latestOf(entries: Entry[]): Entry | null {
  let latest: Entry | null = null;
  for (const entry of entries) {
    if (entry.balance === null) continue;
    if (!latest || entry.date > latest.date) latest = entry;
  }
  return latest;
}

/** One group per account/currency pair the payload actually names. */
function groupsOf(entries: Entry[]): Group[] {
  const byKey = new Map<string, Group>();
  for (const entry of entries) {
    const key = `${entry.account ?? "\u0000"}|${entry.currency ?? "\u0000"}`;
    const group = byKey.get(key) ?? { key, account: entry.account, currency: entry.currency, latest: null };
    if (entry.balance !== null && (!group.latest || entry.date > group.latest.date)) group.latest = entry;
    byKey.set(key, group);
  }
  return [...byKey.values()];
}

function tone(value: number | null): "pos" | "neg" | undefined {
  if (value === null || value === 0) return undefined;
  return value > 0 ? "pos" : "neg";
}

const ENTRY_BASE: DataTableColumn<Entry>[] = [
  {
    key: "date",
    label: "date",
    role: "key",
    cell: (row) => row.date,
    sort: (row) => row.date,
  },
  { key: "kind", label: "kind", cell: (row) => row.kind, sort: (row) => row.kind },
];

function entryCols(hasAccount: boolean, hasCurrency: boolean): DataTableColumn<Entry>[] {
  const cols = [...ENTRY_BASE];
  if (hasAccount) {
    cols.push({ key: "account", label: "account", cell: (row) => row.account ?? DASH, sort: (row) => row.account });
  }
  if (hasCurrency) {
    cols.push({ key: "currency", label: "currency", cell: (row) => row.currency ?? DASH, sort: (row) => row.currency });
  }
  cols.push(
    {
      key: "amount",
      label: "amount",
      num: true,
      cell: (row) => cell(row.amount, "amount"),
      tone: (row) => tone(row.amount),
      sort: (row) => row.amount,
    },
    {
      key: "balance",
      label: "balance",
      num: true,
      cell: (row) => cell(row.balance, "balance"),
      sort: (row) => row.balance,
    },
  );
  return cols;
}

function balanceCols(hasAccount: boolean, hasCurrency: boolean): DataTableColumn<BalanceRow>[] {
  const cols: DataTableColumn<BalanceRow>[] = [];
  if (hasAccount) cols.push({ key: "account", label: "account", role: "key", cell: (row) => row.account });
  if (hasCurrency) cols.push({ key: "currency", label: "currency", cell: (row) => row.currency });
  cols.push(
    { key: "date", label: "latest", num: true, cell: (row) => row.date, sort: (row) => row.date },
    { key: "balance", label: "balance", num: true, cell: (row) => row.balance, sort: (row) => row.balance },
  );
  return cols;
}

/**
 * The `/ledger/cash` payload as a real block: the closing balance on hairlines,
 * one table of balances per account/currency the payload names, and the
 * movements behind them.
 *
 * The read carries no currency code and no account column today. Neither is
 * invented: the currency cell reads `—` with "not in payload" as its reason, and
 * the total is only summed when every group's latest balance is present and no
 * two groups disagree about the currency. A null amount is `—`, never a zero.
 */
function CashLedgerBody({ read, data }: CashLedgerBlockProps) {
  if (!read) {
    return <StateBlock kind="loading" title="Cash ledger" reason={`reading ${ROUTE}`} />;
  }
  if (read.status === "error") {
    return (
      <StateBlock
        kind="error"
        title="Cash ledger could not be read."
        reason={read.lines.join(" ") || `${ROUTE} failed without a message.`}
      />
    );
  }
  if (read.status === "stub") {
    return <StateBlock kind="withheld" title="Cash ledger withheld." reason={read.lines.join(" ")} />;
  }
  if (read.status === "empty") {
    return <StateBlock kind="empty" title="No cash ledger in this read." reason={read.lines.join(" ")} />;
  }
  if (!isRecord(data)) {
    return (
      <StateBlock
        kind="withheld"
        title="Cash ledger withheld."
        reason={`${ROUTE} returned ${data == null ? "no data object" : `a ${Array.isArray(data) ? "list" : typeof data}, not an object`}.`}
      />
    );
  }

  if (!Array.isArray(data.entries)) {
    return (
      <StateBlock
        kind="withheld"
        title="Cash ledger withheld."
        reason={`${ROUTE} · entries ${"entries" in data ? `is a ${typeof data.entries}, not a list` : ABSENT}.`}
      />
    );
  }
  const { entries, skipped } = readEntries(data.entries);
  if (entries.length === 0) {
    return (
      <StateBlock
        kind="empty"
        title="No cash entries in this read."
        reason={`${ROUTE} · entries is empty${skipped > 0 ? ` (${skipped} without a date dropped)` : ""}.`}
      />
    );
  }

  const groups = groupsOf(entries);
  const hasAccount = entries.some((entry) => entry.account !== null);
  const hasCurrency = entries.some((entry) => entry.currency !== null);
  const currencies = [...new Set(groups.map((group) => group.currency).filter((code): code is string => code !== null))];
  const unlabelledCurrency = groups.some((group) => group.currency === null);
  const everyGroupPriced = groups.every((group) => group.latest !== null);
  const totalisable =
    everyGroupPriced && (currencies.length === 0 || (currencies.length === 1 && !unlabelledCurrency));
  const total = totalisable
    ? groups.reduce((sum, group) => sum + (group.latest?.balance ?? 0), 0)
    : null;
  const accounts = new Set(
    entries.map((entry) => entry.account).filter((account): account is string => account !== null),
  ).size;
  const totalNote = totalisable
    ? groups.length === 1
      ? "latest balance"
      : `latest balance · ${groups.length} groups`
    : everyGroupPriced
      ? `no single total across ${currencies.join(" ")}${unlabelledCurrency ? " and an unlabelled currency" : ""}`
      : NO_BALANCE;

  const latest = latestOf(entries);
  const periods = entries.filter((entry) => entry.kind === "period").length;
  const events = entries.length - periods;
  const gaps = entries.filter((entry) => entry.amount === null || entry.balance === null).length;

  const singleCurrency = currencies.length === 1 && !unlabelledCurrency ? currencies[0] ?? null : null;
  const items: KpiCell[] = [
    {
      label: "Closing cash",
      value: total === null ? null : cell(total, "balance"),
      note: totalNote,
    },
    {
      label: "Currency",
      value: singleCurrency,
      note: hasCurrency ? (singleCurrency ? "from the payload" : `${currencies.length} currencies`) : ABSENT,
    },
    {
      label: "Accounts",
      value: hasAccount ? accounts : null,
      note: hasAccount ? undefined : ABSENT,
    },
    {
      label: "Entries",
      value: entries.length,
      note: `${periods} ${periods === 1 ? "period" : "periods"} · ${events} ${events === 1 ? "event" : "events"}`,
    },
    {
      label: "As of",
      value: latest?.date ?? null,
      note: latest ? latest.kind : ABSENT,
    },
  ];

  const balanceRows: BalanceRow[] =
    hasAccount || hasCurrency
      ? groups.map((group) => ({
          id: group.key,
          account: group.account ?? DASH,
          currency: group.currency ?? DASH,
          date: group.latest?.date ?? DASH,
          balance: cell(group.latest?.balance ?? null, "balance"),
          total: false,
        }))
      : [];
  if (balanceRows.length > 1 && total !== null) {
    balanceRows.push({
      id: "total",
      account: "total",
      currency: singleCurrency ?? DASH,
      date: DASH,
      balance: cell(total, "balance"),
      total: true,
    });
  }

  const provenance = read.lines.filter((line) => line.startsWith("source  ") || line.startsWith("marks  "));
  const footer = [
    "cash ledger",
    totalisable ? "closing balances" : "balances not totalled",
    hasCurrency ? null : "no currency code in this payload",
    skipped > 0 ? `${skipped} ${skipped === 1 ? "entry" : "entries"} without a date dropped` : null,
  ]
    .filter((part): part is string => part !== null)
    .join(" · ");

  return (
    <div className="flex flex-col gap-2">
      <KpiGrid items={items} missing={DASH} />
      {balanceRows.length > 0 ? (
        <DataTable
          rows={balanceRows}
          cols={balanceCols(hasAccount, hasCurrency)}
          rowKey={(row) => row.id}
          variant={(row): DataTableRowVariant | undefined => (row.total ? "total" : undefined)}
          label="Cash balances"
          empty="no balances"
        />
      ) : null}
      <DataTable
        rows={entries}
        cols={entryCols(hasAccount, hasCurrency)}
        rowKey={(row) => row.id}
        label="Cash entries"
        empty="no entries"
        stickyFirst
        pageSize={25}
      />
      <p className="m-0 font-mono text-[0.72rem] leading-relaxed text-ink-mute">{footer}</p>
      {provenance.length > 0 ? (
        <p className="m-0 font-mono text-[0.68rem] leading-relaxed text-ink-mute">{provenance.join("   ")}</p>
      ) : null}
      {gaps > 0 ? (
        <p className="m-0 font-mono text-[0.72rem] text-ink-mute">
          {`${DASH} · amount or balance ${ABSENT} on ${gaps} ${gaps === 1 ? "entry" : "entries"}`}
        </p>
      ) : null}
    </div>
  );
}

/** One block throwing on an odd payload must not take the desk down. */
export function CashLedgerBlock({ read, data }: CashLedgerBlockProps) {
  return (
    <BlockBoundary label={ROUTE}>
      <CashLedgerBody read={read} data={data} />
    </BlockBoundary>
  );
}
