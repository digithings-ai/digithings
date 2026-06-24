import { describe, it, expect } from 'vitest';
import { computeFit, computeCenter } from './useCanvasCamera';

describe('computeFit', () => {
  it('returns scale < 1 when bbox is larger than viewport, fitting both axes', () => {
    const result = computeFit({ width: 2000, height: 800 }, { width: 800, height: 400 });
    expect(result.scale).toBeLessThan(1);
    // Must fit width: 800 * scale >= ... actually: bbox * scale <= viewport
    expect(2000 * result.scale).toBeLessThanOrEqual(800 + 1);
    expect(800 * result.scale).toBeLessThanOrEqual(400 + 1);
  });

  it('returns scale = 1 when bbox fits entirely in viewport', () => {
    const result = computeFit({ width: 400, height: 200 }, { width: 800, height: 400 });
    expect(result.scale).toBe(1);
  });

  it('returns a centered translate', () => {
    const result = computeFit({ width: 1000, height: 400 }, { width: 800, height: 400 });
    // translate should be finite numbers
    expect(Number.isFinite(result.x)).toBe(true);
    expect(Number.isFinite(result.y)).toBe(true);
  });
});

describe('computeCenter', () => {
  it('centers a node rect within the viewport at given scale', () => {
    // Node at x=200, y=100, size 160x48, viewport 800x400, scale 1
    const result = computeCenter({ x: 200, y: 100, width: 160, height: 48 }, { width: 800, height: 400 }, 1);
    // Expected: translate so that nodeMidX * scale + tx = vpW/2
    // nodeMidX = 200 + 80 = 280, vpW/2 = 400 → tx = 400 - 280 = 120
    expect(result.x).toBeCloseTo(120);
    // nodeMidY = 100 + 24 = 124, vpH/2 = 200 → ty = 200 - 124 = 76
    expect(result.y).toBeCloseTo(76);
  });

  it('applies scale to the translation', () => {
    const result = computeCenter({ x: 100, y: 0, width: 100, height: 48 }, { width: 800, height: 400 }, 0.5);
    // nodeMidX = 150, at scale 0.5: 150 * 0.5 = 75; tx = 400 - 75 = 325
    expect(result.x).toBeCloseTo(325);
  });
});
