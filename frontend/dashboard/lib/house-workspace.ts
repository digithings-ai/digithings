/**
 * House-book workspace identity for dashboard Group A reads.
 *
 * Matches Python `house_workspace_id()` (uuid5 tenancy namespace + slug `house`)
 * and the migration 096/110 seed. The UUID is public — it is a book selector,
 * not a secret.
 *
 * Migration 109 lets an authenticated Custom member SELECT their own overlay
 * rows *or* house. Date-only `.from('positions')` therefore mixes books on
 * Brief / Holdings / Performance. Every house-dashboard Group A read must go
 * through `houseBook()` so overlay weights never seed the public book.
 *
 * Shared teasers without `workspace_id` (`daily_snapshots`, `theses`,
 * `instruments`) stay date-only. Accounting NAV uses `public_accounting_nav_history`
 * (security definer; house-only until a later view rewrite).
 */

import type { SupabaseClient } from '@supabase/supabase-js';
import type { Database } from './database.types';

export const HOUSE_WORKSPACE_ID = '6b753576-ced9-5319-9bfa-c5d0aacd9319' as const;

/** System corpus workspace (096 seed). Not used on Group A book tables. */
export const SYSTEM_WORKSPACE_ID = '1105372f-4109-5815-be5a-21091ccfc8ad' as const;

export type HouseBookTable =
  | 'positions'
  | 'position_events'
  | 'nav_history'
  | 'portfolio_metrics';

/**
 * PostgREST query pinned to the digithings house book.
 *
 * Overlay workspace rows stay out even when RLS would allow them for the JWT.
 * `select` then `eq` is the supabase-js builder order (FilterBuilder lives on
 * the select result).
 */
export function houseBook(
  sb: SupabaseClient<Database>,
  table: HouseBookTable,
  columns = '*',
) {
  return sb.from(table).select(columns).eq('workspace_id', HOUSE_WORKSPACE_ID);
}
