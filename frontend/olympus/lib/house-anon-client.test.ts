/**
 * House dashboard reads must use the session-less anon client. Auth Pages
 * attach a user JWT; `anon_read` is TO anon only, so the PKCE singleton
 * returns 0 rows (PGRST116 on daily_snapshots.single()) for signed-in users.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));

describe('house anon client wiring', () => {
  it('queries, snapshot, observability, period-status, and pipeline-trace bind supabaseHouse', () => {
    for (const file of [
      'queries.ts',
      'snapshot-fetch.ts',
      'observability-queries.ts',
      'period-status.ts',
      'pipeline-trace.ts',
    ]) {
      const src = readFileSync(join(here, file), 'utf8');
      expect(src, file).toMatch(/supabaseHouse as supabase/);
      expect(src, file).not.toMatch(/import \{ supabase[, }]/);
    }
  });

  it('latest daily_snapshots row uses maybeSingle (0 rows must not 406)', () => {
    const src = readFileSync(join(here, 'queries.ts'), 'utf8');
    expect(src).toContain(
      "from('daily_snapshots').select('id,date,run_type,baseline_date,snapshot,digest_markdown,created_at')",
    );
    expect(src).toMatch(/limit\(1\)\.maybeSingle\(\)/);
    expect(src).not.toMatch(/limit\(1\)\.single\(\)/);
  });
});
