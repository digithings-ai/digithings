import { describe, it, expectTypeOf } from 'vitest';
import type { Thesis, Position, ResearchRunDiagnostics } from './types';

describe('widened domain types (F1)', () => {
  it('Thesis carries the six widened fields', () => {
    expectTypeOf<Thesis>().toHaveProperty('confidence');
    expectTypeOf<Thesis>().toHaveProperty('horizon');
    expectTypeOf<Thesis>().toHaveProperty('thesis_kind');
    expectTypeOf<Thesis>().toHaveProperty('validation_criteria');
    expectTypeOf<Thesis>().toHaveProperty('invalidation_criteria');
    expectTypeOf<Thesis>().toHaveProperty('linked_market_thesis_id');
  });
  it('Position carries conviction + risk envelope', () => {
    expectTypeOf<Position>().toHaveProperty('conviction');
    expectTypeOf<Position>().toHaveProperty('stop_loss_pct');
    expectTypeOf<Position>().toHaveProperty('target_pct_gain');
    expectTypeOf<Position>().toHaveProperty('horizon_days');
    expectTypeOf<Position>().toHaveProperty('sector_bucket');
  });
  it('ResearchRunDiagnostics carries run economics', () => {
    expectTypeOf<ResearchRunDiagnostics>().toHaveProperty('est_cost_usd');
    expectTypeOf<ResearchRunDiagnostics>().toHaveProperty('cached_tokens');
  });
});
