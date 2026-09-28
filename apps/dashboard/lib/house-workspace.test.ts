import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  HOUSE_WORKSPACE_ID,
  SYSTEM_WORKSPACE_ID,
  houseBook,
  type HouseBookTable,
} from './house-workspace';

const here = dirname(fileURLToPath(import.meta.url));

const GROUP_A_TABLES: readonly HouseBookTable[] = [
  'positions',
  'position_events',
  'nav_history',
  'portfolio_metrics',
];

describe('house workspace identity', () => {
  it('matches the migration 096/110 house and system seeds', () => {
    expect(HOUSE_WORKSPACE_ID).toBe('6b753576-ced9-5319-9bfa-c5d0aacd9319');
    expect(SYSTEM_WORKSPACE_ID).toBe('1105372f-4109-5815-be5a-21091ccfc8ad');
    expect(HOUSE_WORKSPACE_ID).not.toBe(SYSTEM_WORKSPACE_ID);
  });

  it('pins workspace_id after select', () => {
    const calls: Array<[string, string]> = [];
    const sb = {
      from(table: string) {
        return {
          select(_columns: string) {
            return {
              eq(column: string, value: string) {
                calls.push([column, value]);
                return { table, column, value };
              },
            };
          },
        };
      },
    };
    const scoped = houseBook(sb as never, 'positions');
    expect(calls).toEqual([['workspace_id', HOUSE_WORKSPACE_ID]]);
    expect(scoped).toEqual({
      table: 'positions',
      column: 'workspace_id',
      value: HOUSE_WORKSPACE_ID,
    });
  });
});

describe('dashboard Group A readers go through the Workers API house pin', () => {
  const files = ['queries.ts', 'observability-queries.ts'] as const;

  it.each(files)('%s has no raw Group A .from() and uses apiHouseBook()', (file) => {
    const src = readFileSync(join(here, file), 'utf8');
    // All reads go through the Workers API query root; the house workspace
    // pin is enforced server-side (CONTRACT §7), not by a client helper.
    expect(src).toContain("from './api-query'");
    expect(src).toContain('apiHouseBook(');
    expect(src).not.toContain("from './house-workspace'");
    expect(src).not.toContain('houseBook(');
    for (const table of GROUP_A_TABLES) {
      const rawFrom = new RegExp(`\\.from\\(['"]${table}['"]\\)`, 'g');
      expect(src.match(rawFrom) ?? [], `${file} still has raw .from('${table}')`).toEqual([]);
      // Comments may mention nav_history without querying it (accounting view path).
      const queriesTable =
        table !== 'nav_history' &&
        (src.includes(`'${table}'`) || src.includes(`"${table}"`));
      if (queriesTable) {
        const houseCall = new RegExp(`apiHouseBook\\(\\s*['"]${table}['"]`);
        expect(src, `${file} must call apiHouseBook('${table}')`).toMatch(houseCall);
      }
    }
  });
});
