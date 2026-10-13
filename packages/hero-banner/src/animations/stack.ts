import { emptyFrame, litCells, mulberry32, setPixel } from "../layout";
import type { Animation, Frame, Layout, Pixel } from "../types";

/**
 * STACK (digibase). Every pixel row is a table row; every run of lit cells in
 * it, cut to at most `blockMax` pixels, is a record.
 * LOADING: rows are written bottom-up. Inside a row the write cursor goes left
 * to right, and each record drops in from above the word under gravity and
 * lands in `accent` (written, not committed). Because the rows fill from the
 * bottom, a record never has to fall through one that has already landed.
 * When the last record of a row lands, the row commits: it flashes `glint` and
 * cools to ink. The commits climb the word like a table filling up.
 * LIVE: transactions. An UPDATE rewrites one to three neighbouring records in a
 * row (they drop back to `accent`, then commit again); one in three is a SCAN,
 * a cursor running along a row and lighting the empty cells it passes.
 */

export type StackOptions = {
  /** Delay between one row and the row above it starting to write. */
  rowMs: number;
  /** ms for the write cursor to cross the word inside one row. */
  sweepMs: number;
  /** ms for a record to fall the full height of the word. */
  fallMs: number;
  /** Longest record, in pixels. Longer runs are cut. */
  blockMax: number;
  /** Pause between a row's last record landing and its commit. */
  holdMs: number;
  /** Length of the commit flash, `glint` cooling to ink. */
  commitMs: number;
  /** LIVE: ms between transactions. */
  txEveryMs: number;
  /** LIVE: ms an updated record stays written-not-committed. */
  txWriteMs: number;
  /** LIVE: ms for a scan to cross the word. */
  scanMs: number;
};

export type StackRecord = { y: number; x0: number; x1: number; start: number; land: number };

type Tx = { at: number; y: number; first: number; count: number; scan: boolean };

export type StackState = {
  width: number;
  height: number;
  lit: Uint8Array;
  records: StackRecord[];
  /** Index of the records in each pixel row, left to right. */
  rows: number[][];
  /** Commit time of each pixel row; -Infinity for a row with no records. */
  commit: number[];
  seed: number;
  options: StackOptions;
  ms: number;
};

export function stackAnimation(options: StackOptions): Animation<StackState> {
  return {
    kind: "stack",
    liveTickMs: 50,
    prepare(layout: Layout, def) {
      const { width, height } = layout;
      const rand = mulberry32(def.seed);
      const lit = new Uint8Array(width * height);
      for (const cell of litCells(layout)) lit[cell.y * width + cell.x] = 1;
      const records: StackRecord[] = [];
      const rows: number[][] = Array.from({ length: height }, () => []);
      const commit: number[] = Array(height).fill(Number.NEGATIVE_INFINITY);
      for (let y = height - 1; y >= 0; y -= 1) {
        const level = height - 1 - y;
        for (let x = 0; x < width; ) {
          if (!lit[y * width + x]) {
            x += 1;
            continue;
          }
          let end = x;
          while (end + 1 < width && lit[y * width + end + 1] && end + 1 - x < options.blockMax) end += 1;
          // A little seeded slack so a row does not land as one rigid comb.
          const start = Math.round(level * options.rowMs + (x / width) * options.sweepMs + rand() * options.rowMs * 0.25);
          const land = start + fallTime(options, y + 1, height);
          rows[y].push(records.length);
          records.push({ y, x0: x, x1: end, start, land });
          x = end + 1;
        }
        if (rows[y].length) commit[y] = Math.max(...rows[y].map((i) => records[i].land)) + options.holdMs;
      }
      const ms = Math.ceil(Math.max(...commit) + options.commitMs);
      return { width, height, lit, records, rows, commit, seed: def.seed, options, ms };
    },
    loadingMs: (state) => state.ms,
    loading,
    live,
    still: settled,
  };
}

/** Time to fall `distance` pixel rows from just above the word: t grows with the
 *  square root of the distance, as under gravity. */
function fallTime(options: StackOptions, distance: number, height: number): number {
  return options.fallMs * Math.sqrt(distance / (height + 1));
}

/** Row a falling record's top sits on at `t`, before it lands. Starts above the word. */
function fallRow(record: StackRecord, t: number): number {
  const total = record.land - record.start;
  const p = Math.min(1, Math.max(0, (t - record.start) / total));
  // Ease-in (p^2): slow off the top, fast into the stack.
  return Math.floor(-1 + p * p * (record.y + 1));
}

/** The commit flash: glint at the commit, ink after `commitMs`. */
function committed(state: StackState, since: number): Pixel {
  const k = since / state.options.commitMs;
  if (k >= 1) return { tone: "ink", alpha: 1 };
  return k < 0.35 ? { tone: "glint", alpha: 1 } : { tone: "ink", alpha: 1 };
}

function loading(state: StackState, t: number): Frame {
  const frame = emptyFrame(state.width, state.height);
  // Falling records first, so a landed cell always wins the pixel.
  const landed: StackRecord[] = [];
  for (const record of state.records) {
    if (t < record.start) continue;
    if (t >= record.land) {
      landed.push(record);
      continue;
    }
    const y = fallRow(record, t);
    if (y < 0) continue;
    for (let x = record.x0; x <= record.x1; x += 1) setPixel(frame, x, y, { tone: "accent", alpha: 1 });
    // A faint wake one row up shows the drop direction.
    if (y > 0) for (let x = record.x0; x <= record.x1; x += 1) setPixel(frame, x, y - 1, { tone: "accent", alpha: 0.25 });
  }
  for (const record of landed) {
    const since = t - state.commit[record.y];
    const pixel = since >= 0 ? committed(state, since) : { tone: "accent", alpha: 1 };
    for (let x = record.x0; x <= record.x1; x += 1) setPixel(frame, x, record.y, pixel);
  }
  return frame;
}

function settled(state: StackState): Frame {
  const frame = emptyFrame(state.width, state.height);
  for (const record of state.records) {
    for (let x = record.x0; x <= record.x1; x += 1) setPixel(frame, x, record.y, { tone: "ink", alpha: 1 });
  }
  return frame;
}

/** Transaction `i` of the LIVE schedule. Seeded per index, so any moment can be sampled. */
function transaction(state: StackState, i: number): Tx {
  const rand = mulberry32((state.seed ^ Math.imul(i + 1, 0x9e3779b1)) >>> 0);
  const { txEveryMs } = state.options;
  const at = i * txEveryMs + Math.floor(rand() * txEveryMs * 0.5);
  const scan = rand() < 1 / 3;
  const filled = state.rows.map((r, y) => (r.length ? y : -1)).filter((y) => y >= 0);
  const y = filled[Math.floor(rand() * filled.length)];
  const count = 1 + Math.floor(rand() * 3);
  const first = Math.floor(rand() * Math.max(1, state.rows[y].length - count + 1));
  return { at, y, first, count, scan };
}

function live(state: StackState, tLive: number): Frame {
  const frame = settled(state);
  const { txEveryMs, txWriteMs, commitMs, scanMs } = state.options;
  const life = Math.max(txWriteMs + commitMs, scanMs * 1.2);
  const firstTx = Math.max(0, Math.floor((tLive - life) / txEveryMs) - 1);
  const lastTx = Math.floor(tLive / txEveryMs);
  for (let i = firstTx; i <= lastTx; i += 1) {
    const tx = transaction(state, i);
    const age = tLive - tx.at;
    if (age < 0 || age > life) continue;
    if (tx.scan) {
      const head = Math.round((age / scanMs) * (state.width + 4)) - 2;
      for (let k = 0; k < 4; k += 1) {
        const x = head - k;
        if (x < 0 || x >= state.width) continue;
        if (state.lit[tx.y * state.width + x]) setPixel(frame, x, tx.y, { tone: "glint", alpha: 1 });
        else setPixel(frame, x, tx.y, { tone: "accent", alpha: k === 0 ? 0.9 : 0.5 * (1 - k / 4) });
      }
      continue;
    }
    const pixel = age < txWriteMs ? { tone: "accent", alpha: 1 } : committed(state, age - txWriteMs);
    for (const index of state.rows[tx.y].slice(tx.first, tx.first + tx.count)) {
      const record = state.records[index];
      for (let x = record.x0; x <= record.x1; x += 1) setPixel(frame, x, record.y, pixel);
    }
  }
  return frame;
}
