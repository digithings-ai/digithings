import { describe, it, expect } from 'vitest';
import { WHY_TABS, resolveWhyTab } from './why-tabs';

describe('WHY_TABS', () => {
  it('is read · deliberations, in order (Documents archive retired)', () => {
    expect(WHY_TABS.map((t) => t.id)).toEqual(['read', 'deliberations']);
    expect(WHY_TABS.map((t) => t.label)).toEqual(['The read', 'Deliberations']);
  });
});

describe('resolveWhyTab', () => {
  it('defaults to The read', () => {
    expect(resolveWhyTab({})).toBe('read');
  });

  it('honors an explicit why param', () => {
    expect(resolveWhyTab({ why: 'deliberations' })).toBe('deliberations');
    expect(resolveWhyTab({ why: 'read' })).toBe('read');
  });

  it('falls back to The read for an unknown why param (e.g. the retired documents tab)', () => {
    expect(resolveWhyTab({ why: 'documents' })).toBe('read');
  });
});
