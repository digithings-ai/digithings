/**
 * Tearsheet trade log — every round trip as a row: direction pill (long
 * wears --up, short --down), dates, entry/mark, and a toned return cell.
 * Cells are ReactNodes, so the open position renders its unrealized mark
 * with a tag and the whole row wears the accent-washed `.ts-trade-open`
 * state, sorted to the top. The mono thead is sticky inside a scroll clamp
 * on screen; in print the clamp opens, the head goes static, and rows never
 * split across pages. Static display template.
 */
import {
  DirectionPill,
  TEARSHEET_DEMO,
  TradeLogTable,
  fmtNum,
  fmtPct,
  isOpenTrade,
  toneClass,
  type TradeLogRow,
} from "@digithings/web";

const D = TEARSHEET_DEMO;

function tradeDate(t: (typeof D.trades)[number]): string {
  if (isOpenTrade(t)) return `${t.entry_date} → open`;
  return t.exit_date;
}

export function TearsheetTradeLogReference() {
  // Open position first, then closed trades newest → oldest — the tearsheet
  // log order. Sorting is page wiring; the table renders what it is given.
  const sorted = [...D.trades].sort((a, b) => {
    const aOpen = isOpenTrade(a);
    const bOpen = isOpenTrade(b);
    if (aOpen !== bOpen) return aOpen ? -1 : 1;
    return (b.exit_date || b.entry_date).localeCompare(a.exit_date || a.entry_date);
  });

  const rows: TradeLogRow[] = sorted.slice(0, 14).map((t) => {
    const open = isOpenTrade(t);
    return {
      key: t.n,
      open,
      cells: [
        <DirectionPill key="dir" direction={t.direction} />,
        tradeDate(t),
        D.symbol.split("-")[0],
        fmtNum(t.entry_price, 2),
        fmtNum(t.exit_price, 2),
        open ? (
          <span key="ret" className="ts-trade-unrealized">
            <span className={toneClass(t.pnl_pct)}>{fmtPct(t.pnl_pct)}</span>
            <span className="ts-trade-unrealized-tag">unrealized</span>
          </span>
        ) : (
          <span key="ret" className={toneClass(t.pnl_pct)}>{fmtPct(t.pnl_pct)}</span>
        ),
      ],
    };
  });

  return (
    <TradeLogTable
      columns={[
        { label: "Direction" },
        { label: "Date" },
        { label: "Asset" },
        { label: "Entry", numeric: true },
        { label: "Mark", numeric: true },
        { label: "Return", numeric: true },
      ]}
      rows={rows}
    />
  );
}
