import { describe, it, expect } from 'vitest';
import { NAV } from './nav';

describe('NAV', () => {
  it('is the 4-destination owner spine, in order', () => {
    expect(NAV.map((n) => n.href)).toEqual(['/', '/portfolio', '/pipeline', '/system']);
    expect(NAV.map((n) => n.label)).toEqual(['Brief', 'Portfolio', 'Pipeline', 'System']);
  });

  it('demotes only System', () => {
    expect(NAV.filter((n) => n.demoted).map((n) => n.href)).toEqual(['/system']);
  });

  it('gives every item a renderable icon', () => {
    expect(NAV.every((n) => typeof n.icon === 'function' || typeof n.icon === 'object')).toBe(true);
  });
});
