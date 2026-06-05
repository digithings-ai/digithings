/**
 * REM-036 — optional BFF snapshot read (service role, server-only).
 *
 * Static export (`output: 'export'`) omits this route; enable when hosting
 * Olympus on Node (`npm run dev` / non-export deploy) with
 * `NEXT_PUBLIC_OLYMPUS_USE_BFF=1`.
 */
import { createClient } from '@supabase/supabase-js';
import { NextResponse } from 'next/server';
import type { Database } from '@/lib/database.types';

export const dynamic = 'force-dynamic';

export async function GET() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const serviceKey = process.env.OLYMPUS_SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!url || !serviceKey) {
    return NextResponse.json({ snapshot: null }, { status: 404 });
  }
  const client = createClient<Database>(url, serviceKey);
  const { data, error } = await client
    .from('daily_snapshots')
    .select('date, run_type, baseline_date, snapshot, created_at')
    .order('date', { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) {
    return NextResponse.json({ message: error.message }, { status: 502 });
  }
  return NextResponse.json({ snapshot: data ?? null });
}
