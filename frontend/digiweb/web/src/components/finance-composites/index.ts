/**
 * Finance-composites family barrel (#1450) — the composite finance surfaces
 * promoted from the reference finance/data pages: ticker tape, order book,
 * sortable leaderboard, book-level performance dashboard, and the synced
 * two-pane tearsheet chart. Structural CSS: styles/finance-composites.css.
 * Re-exported from the package barrel (src/index.ts) by the F1 wire-up.
 */
export { StockTicker, type TickerItem, type StockTickerProps } from "./StockTicker";
export { OrderBook, type OrderBookLevel, type OrderBookProps } from "./OrderBook";
export { SortableTable, type SortableColumn, type SortableTableProps } from "./SortableTable";
