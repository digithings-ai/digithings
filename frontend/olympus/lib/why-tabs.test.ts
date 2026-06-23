import { describe, it, expect } from 'vitest';
import { WHY_TABS, resolveWhyTab } from './why-tabs';

describe('WHY_TABS', () => {
  it('is read · deliberations · documents, in order', () => {
    expect(WHY_TABS.map((t) => t.id)).toEqual(['read', 'deliberations', 'documents']);
    expect(WHY_TABS.map((t) => t.label)).toEqual(['The read', 'Deliberations', 'Documents']);
  });
});

describe('resolveWhyTab', () => {
  it('defaults to The read', () => {
    expect(resolveWhyTab({})).toBe('read');
  });

  it('honors an explicit why param', () => {
    expect(resolveWhyTab({ why: 'deliberations' })).toBe('deliberations');
    expect(resolveWhyTab({ why: 'documents' })).toBe('documents');
  });

  it('lands legacy research/library deep links on Documents', () => {
    expect(resolveWhyTab({ tab: 'daily' })).toBe('documents');
    expect(resolveWhyTab({ docKey: 'digest' })).toBe('documents');
    expect(resolveWhyTab({ date: '2026-06-22' })).toBe('documents');
  });

  it('lets an explicit why override legacy params', () => {
    expect(resolveWhyTab({ why: 'read', tab: 'daily' })).toBe('read');
  });
});
