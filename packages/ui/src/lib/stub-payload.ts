/**
 * The one stub detector for every digiquant surface.
 *
 * Four surfaces painted the same "is this the stub envelope?" rule and drifted
 * apart while they did it. Three of them matched numbers by value, one matched
 * them as substrings of the serialised payload, and the substring copy is what
 * put a stub banner over a live NAV block: a real figure that merely contained
 * the fixture's digits (`204.045`, `1204.04`, `154.10`, `180.5`, `54.15`) read as
 * the fixture. Every rule here is value-exact instead, so a longer number that
 * only contains those digits is not the fixture.
 *
 * Two input shapes are accepted, because the surfaces do not agree on one:
 *
 * - A parsed payload (object or array). Checked structurally: numbers by value,
 *   the fixture's string spellings as whole values, and the two fixture row
 *   shapes as row conjunctions rather than as text.
 * - Display lines (`string[]`, or a bare string). Checked per line by numeric
 *   token, deliberately without the row conjunctions: a painted line carries
 *   bare numbers, so a conjunction over them would be a guess. The surfaces that
 *   hand over display lines have already run the structural check on the payload
 *   they painted from, so nothing is lost.
 */

/**
 * NAV values the dashboard-api stub fixtures emit. A live series never lands on
 * one of these exactly.
 */
const STUB_NAV_VALUES = [99.909, 204.04];

/**
 * Since-inception style figures the stub fixtures emit. Matched by value so a
 * live percentage that merely starts with the same digits is not the fixture.
 */
const STUB_SINCE_INCEPTION_VALUES = [103.040192, 104.44808, 3.040191838399986];

/**
 * String spellings the fixtures emit. Matched as whole values only, so the
 * padded `204.040` is the fixture and a longer string that contains it is not.
 */
const STUB_TEXT_VALUES = new Set(["99.909", "204.04", "204.040"]);

/**
 * The only benchmark tape the stub fixtures emit. All three parts are required,
 * exactly as the four copies required them: a tape that happens to close at 500
 * on that date is a real tape until it also closes at 515.
 */
const STUB_TAPE_DATE = "2026-08-20";
const STUB_TAPE_CLOSES = [500, 515];

/**
 * The two ledger rows the stub fixture always emits together. One row alone is
 * ordinary house activity, so both are required.
 */
const STUB_LEDGER_ROWS = [
  { date: "2026-09-03", ticker: "XLF", value: 54.1 },
  { date: "2026-06-01", ticker: "GLD", value: 180 },
];

/** JSON round-trips a float through its shortest form, so this only absorbs that. */
const EPSILON = 1e-6;

/** A numeric literal inside a painted line. Signs are kept so `-54.15` stays negative. */
const NUMBER_TOKEN = /[-+]?\d+(?:\.\d+)?/g;

function near(value: number, target: number): boolean {
  return Math.abs(value - target) < EPSILON;
}

/** True when `value` is one of the fixture's figures, to the precision JSON can carry. */
function isStubNumber(value: number): boolean {
  return (
    STUB_NAV_VALUES.some((target) => near(value, target)) ||
    STUB_SINCE_INCEPTION_VALUES.some((target) => near(value, target))
  );
}

/** Every number painted in a display line, as values rather than as digit runs. */
function numbersIn(text: string): number[] {
  return (text.match(NUMBER_TOKEN) ?? [])
    .map(Number)
    .filter((value) => Number.isFinite(value));
}

/** A fixture NAV carried as a string rather than as a number. */
function isStubTextValue(value: string): boolean {
  return STUB_TEXT_VALUES.has(value.trim());
}

/** The price of a ledger row. The surfaces name it `price` or `fill_price`. */
function rowPrice(row: Record<string, unknown>): number | null {
  for (const key of ["price", "fill_price"]) {
    const value = row[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() !== "") {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return null;
}

function matchesLedgerRow(row: Record<string, unknown>, expected: (typeof STUB_LEDGER_ROWS)[number]): boolean {
  const price = rowPrice(row);
  return (
    price != null &&
    near(price, expected.value) &&
    row.date === expected.date &&
    row.ticker === expected.ticker
  );
}

/** Records whichever parts of the stub tape this row carries. */
function noteStubTapeRow(row: Record<string, unknown>, out: Scan): void {
  if (row.date === STUB_TAPE_DATE) out.tapeDate = true;
  const close = row.close;
  if (typeof close !== "number" || !Number.isFinite(close)) return;
  STUB_TAPE_CLOSES.forEach((target, index) => {
    if (near(close, target)) out.tapeCloses.add(index);
  });
}

/** What one walk of a parsed payload found. The ledger rows accumulate across the whole tree. */
interface Scan {
  stubValue: boolean;
  tapeDate: boolean;
  tapeCloses: Set<number>;
  ledgerRows: Set<number>;
}

function scan(value: unknown, seen: Set<object>, out: Scan): void {
  if (typeof value === "number") {
    if (isStubNumber(value)) out.stubValue = true;
    return;
  }
  if (typeof value === "string") {
    if (isStubTextValue(value)) out.stubValue = true;
    return;
  }
  if (value == null || typeof value !== "object") return;
  if (seen.has(value)) return;
  seen.add(value);

  if (Array.isArray(value)) {
    for (const item of value) scan(item, seen, out);
    return;
  }

  const record = value as Record<string, unknown>;
  noteStubTapeRow(record, out);
  STUB_LEDGER_ROWS.forEach((expected, index) => {
    if (!out.ledgerRows.has(index) && matchesLedgerRow(record, expected)) out.ledgerRows.add(index);
  });
  for (const nested of Object.values(record)) scan(nested, seen, out);
}

/**
 * True when `payload` is the dashboard-api stub envelope rather than a house read.
 *
 * A `legacy_estimate` contract on its own is NOT a stub: three of the four
 * surfaces that painted this rule never treated it as one, and a house NAV series
 * carries that contract on real points. It only appears in fixtures alongside one
 * of the figures above, which is where it is caught.
 */
export function isStubPayload(payload: unknown): boolean {
  if (typeof payload === "string") return isStubLine(payload);
  if (Array.isArray(payload) && payload.every((line) => typeof line === "string")) {
    return (payload as string[]).some(isStubLine);
  }

  const out: Scan = { stubValue: false, tapeDate: false, tapeCloses: new Set(), ledgerRows: new Set() };
  scan(payload, new Set<object>(), out);
  const isStubTape = out.tapeDate && out.tapeCloses.size === STUB_TAPE_CLOSES.length;
  return out.stubValue || isStubTape || out.ledgerRows.size === STUB_LEDGER_ROWS.length;
}

/**
 * A painted display line is stub evidence only when it carries a fixture figure
 * as a value. The row conjunctions are deliberately not re-applied here: a line
 * holds bare numbers, so requiring them would be a guess about the format.
 */
function isStubLine(line: string): boolean {
  return numbersIn(line).some(isStubNumber);
}