/**
 * #3983 — the realized-attribution read must not silently truncate at a single
 * PostgREST page. `collectPagedRows` is the shared paging loop; these lock its
 * stop/flag semantics.
 */
import { describe, expect, it } from 'vitest';
import { collectPagedRows } from './observability-queries';

describe('collectPagedRows (#3983)', () => {
  it('concatenates full pages until a short page', async () => {
    const pages: number[][] = [[1, 2, 3], [4, 5], [6]];
    const ranges: Array<[number, number]> = [];
    const result = await collectPagedRows<number>(3, 100, async (from, to) => {
      ranges.push([from, to]);
      return { rows: pages.shift() ?? [], ok: true };
    });

    expect(result).toEqual({ rows: [1, 2, 3, 4, 5], ok: true, truncated: false });
    expect(ranges).toEqual([
      [0, 2],
      [3, 5],
    ]);
  });

  it('flags truncation when the cap is reached on a full page', async () => {
    const result = await collectPagedRows<number>(2, 4, async (from) => ({
      rows: [from, from + 1],
      ok: true,
    }));

    expect(result).toEqual({ rows: [0, 1, 2, 3], ok: true, truncated: true });
  });

  it('stops on the first failed page and reports not-ok', async () => {
    let calls = 0;
    const result = await collectPagedRows<number>(2, 100, async () => {
      calls += 1;
      return calls === 1 ? { rows: [1, 2], ok: true } : { rows: [], ok: false };
    });

    expect(result).toEqual({ rows: [1, 2], ok: false, truncated: false });
  });
});
