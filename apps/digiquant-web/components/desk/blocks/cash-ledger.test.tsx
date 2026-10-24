import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { STUB_READ, type ReadResult } from "digiquant-tui/read";
import { CashLedgerBlock } from "./cash-ledger";

const OK: ReadResult = { status: "ok", lines: [], asOf: "2026-09-24" };

/** The payload `/ledger/cash` serves today: no currency, no account. */
const PAYLOAD = {
  entries: [
    { date: "2026-09-24", kind: "period", amount: 5, balance: 105 },
    { date: "2026-09-17", kind: "period", amount: 2.5, balance: 100 },
    { date: "2026-09-10", kind: "dividend", amount: -12.5, balance: 97.5 },
  ],
};

const render = (read: ReadResult | undefined, data?: unknown) =>
  renderToStaticMarkup(<CashLedgerBlock read={read} data={data} />);

describe("cash ledger block", () => {
  it("paints the closing balance, the entry count and the movements", () => {
    const html = render(OK, PAYLOAD);
    expect(html).toContain("Closing cash");
    // 105 is the latest balance and the only group, so it is the total.
    expect(html).toContain("105.00");
    expect(html).toContain("Entries");
    expect(html).toContain("3");
    expect(html).toContain("2 periods · 1 event");
    expect(html).toContain("As of");
    expect(html).toContain("2026-09-24");
    // Every entry is a row, with the signed amount in its money tone.
    expect(html).toContain("2026-09-17");
    expect(html).toContain("dividend");
    expect(html).toContain("-12.50");
    expect(html).toContain("text-down");
    // The latest balance is the total, so the balance table is not needed and
    // neither column is invented.
    expect(html).not.toContain(">account<");
    expect(html).not.toContain(">currency<");
  });

  it("never invents a currency the payload did not carry", () => {
    const html = render(OK, PAYLOAD);
    expect(html).toContain("Currency");
    expect(html).toContain("not in payload");
    expect(html).toContain("no currency code in this payload");
    // No dollar, euro or pound sign anywhere.
    expect(html).not.toMatch(/[$€£¥]/);
    // The accounts cell is absent for the same reason.
    expect(html).toContain("Accounts");
  });

  it("groups per account and currency when the payload names them", () => {
    const html = render(OK, {
      entries: [
        { date: "2026-09-24", kind: "period", account: "main", currency: "USD", amount: 5, balance: 105 },
        { date: "2026-09-23", kind: "period", account: "main", currency: "USD", amount: 1, balance: 100 },
        { date: "2026-09-22", kind: "period", account: "fx", currency: "EUR", amount: 2, balance: 40 },
      ],
    });
    expect(html).toContain("USD");
    expect(html).toContain("EUR");
    expect(html).toContain("main");
    expect(html).toContain("fx");
    expect(html).toContain("2 currencies");
    // Two currencies never get one invented total.
    expect(html).toContain("no single total across USD EUR");
    expect(html).toContain("balances not totalled");
  });

  it("totals the latest balance per account when the currency is the same", () => {
    const html = render(OK, {
      entries: [
        { date: "2026-09-24", kind: "period", account: "main", currency: "USD", balance: 100 },
        { date: "2026-09-23", kind: "period", account: "reserve", currency: "USD", balance: 50 },
      ],
    });
    expect(html).toContain("150.00");
    expect(html).toContain(">total<");
    expect(html).toContain("latest balance · 2 groups");
  });

  it("says the read is empty instead of painting a zero", () => {
    const read = render({ status: "empty", lines: ["This read returned no values."], asOf: null }, { entries: [] });
    expect(read).toContain('data-state="empty"');
    expect(read).toContain("No cash ledger in this read.");
    expect(read).not.toContain("Closing cash");

    // An ok read that carries an empty list says that, not "no values".
    const empty = render(OK, { entries: [] });
    expect(empty).toContain('data-state="empty"');
    expect(empty).toContain("No cash entries in this read.");
    expect(empty).toContain("entries is empty");
  });

  it("announces an error and repeats the route's own message", () => {
    const html = render({ status: "error", lines: ["/ledger/cash failed (403): forbidden"], asOf: null }, null);
    expect(html).toContain('role="alert"');
    expect(html).toContain("[!]");
    expect(html).toContain("Cash ledger could not be read.");
    expect(html).toContain("/ledger/cash failed (403): forbidden");
    expect(html).not.toContain("Closing cash");
  });

  it("withholds a stub envelope rather than showing its numbers", () => {
    const html = render({ status: "stub", lines: [STUB_READ], asOf: null }, PAYLOAD);
    expect(html).toContain('data-state="withheld"');
    expect(html).toContain("Cash ledger withheld.");
    expect(html).toContain(STUB_READ);
    expect(html).not.toContain("105.00");
  });

  it("reads as loading before the first response lands", () => {
    const html = render(undefined, undefined);
    expect(html).toContain('data-state="loading"');
    expect(html).toContain("reading /ledger/cash");
  });

  it("leaves a null balance as — with its reason, never as a zero", () => {
    const html = render(OK, {
      entries: [
        { date: "2026-09-24", kind: "period", account: "main", amount: 5, balance: null },
        { date: "2026-09-17", kind: "period", account: "reserve", amount: null, balance: 100 },
      ],
    });
    expect(html).toContain("—");
    expect(html).toContain("no latest balance for every account");
    expect(html).toContain("amount or balance not in payload on 2 entries");
    // The one balance the payload holds is printed; nothing is zero-filled.
    expect(html).toContain("100.00");
    expect(html).not.toMatch(/>0\.00</);
  });

  it("names an entry it had to drop instead of silently shrinking the ledger", () => {
    const html = render(OK, {
      entries: [
        { date: "2026-09-24", kind: "period", amount: 5, balance: 105 },
        { kind: "period", amount: 1, balance: 100 },
        "nonsense",
      ],
    });
    expect(html).toContain("2 entries without a date dropped");
    expect(html).toContain("105.00");
  });

  it("withholds a payload that is not an object", () => {
    const list = render(OK, [1, 2, 3]);
    expect(list).toContain('data-state="withheld"');
    expect(list).toContain("a list, not an object");
    const absent = render(OK, { unexpected: true });
    expect(absent).toContain("entries not in payload");
  });
});
