/**
 * Number formatting shared by the finance-tearsheet charts, tables, and card
 * KPIs (#1463) — verbatim from
 * frontend/digiquant-web/components/tearsheet/format.ts so promoted surfaces
 * render figure-for-figure identical.
 */

/** Compact axis/KPI formatting so huge compounded figures never overflow. */
export function fmtCompact(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "";
  const a = Math.abs(v);
  if (a >= 1e9) return (v / 1e9).toFixed(a >= 1e10 ? 0 : 1) + "B";
  if (a >= 1e6) return (v / 1e6).toFixed(a >= 1e7 ? 0 : 1) + "M";
  if (a >= 1e3) return (v / 1e3).toFixed(a >= 1e4 ? 0 : 1) + "K";
  if (a >= 1) return v.toFixed(0);
  if (a === 0) return "0";
  return v.toFixed(2);
}

export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "n/a";
  if (Math.abs(v) >= 10000) return fmtCompact(v) + "%";
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "%";
}

export function fmtMoney(v: number | null | undefined): string {
  if (v === null || v === undefined) return "n/a";
  if (Math.abs(v) >= 100000) return fmtCompact(v);
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtNum(v: number | null | undefined, d = 0): string {
  if (v === null || v === undefined) return "n/a";
  return v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}

/** Money tone class for a signed value: `.is-pos` / `.is-neg` / none at 0. */
export function toneClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return "";
  return v > 0 ? "is-pos" : v < 0 ? "is-neg" : "";
}
