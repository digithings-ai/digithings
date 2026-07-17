import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { computeFit, computeCenter, computeZoomToward, clampScale, exceedsDragSlop } from './useCanvasCamera';

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

describe('clampScale', () => {
  it('clamps below the minimum', () => {
    expect(clampScale(0.1)).toBeCloseTo(0.4);
  });
  it('clamps above the maximum', () => {
    expect(clampScale(10)).toBeCloseTo(2.5);
  });
  it('passes through an in-range value', () => {
    expect(clampScale(1.3)).toBeCloseTo(1.3);
  });
});

describe('computeZoomToward', () => {
  it('keeps the anchor point fixed in screen space', () => {
    const prev = { x: 0, y: 0, scale: 1 };
    // World point under the cursor: (originX - x) / scale = 200.
    const next = computeZoomToward(prev, 2, 200, 100);
    // After zoom, the same world point must still land under (200,100):
    // screenX = worldX * scale + x = 200 * 2 + next.x  ⇒ must equal 200.
    expect(200 * 2 + next.x).toBeCloseTo(200);
    // worldY = (100 - 0) / 1 = 100; after zoom: 100 * 2 + next.y must equal 100.
    expect(100 * 2 + next.y).toBeCloseTo(100);
  });

  it('preserves the world point under the cursor exactly', () => {
    const prev = { x: 30, y: 10, scale: 1.2 };
    const originX = 250;
    const originY = 140;
    const worldX = (originX - prev.x) / prev.scale;
    const worldY = (originY - prev.y) / prev.scale;
    const next = computeZoomToward(prev, 1.8, originX, originY);
    expect(worldX * next.scale + next.x).toBeCloseTo(originX);
    expect(worldY * next.scale + next.y).toBeCloseTo(originY);
  });

  it('clamps the resulting scale', () => {
    const next = computeZoomToward({ x: 0, y: 0, scale: 2.4 }, 99, 0, 0);
    expect(next.scale).toBeCloseTo(2.5);
  });
});

describe('drag slop — clicks must reach canvas nodes (#1553)', () => {
  it('sub-slop movement is a click-in-progress, not a pan', () => {
    expect(exceedsDragSlop(100, 100, 100, 100)).toBe(false);
    expect(exceedsDragSlop(100, 100, 102, 102)).toBe(false); // ~2.8px
    expect(exceedsDragSlop(100, 100, 104, 100)).toBe(true);  // 4px
    expect(exceedsDragSlop(100, 100, 90, 110)).toBe(true);
  });

  it('never captures the pointer on pointerdown (capture retargets click to the viewport)', () => {
    // Regression pin, canon-test style (precedent: lw-chart-canon.test.ts).
    // Capturing in onPointerDown swallowed every node click on the canvas —
    // documents could only be opened via keyboard. Capture is only legal
    // inside onPointerMove, after the slop check.
    const src = readFileSync(join(__dirname, 'useCanvasCamera.ts'), 'utf8');
    const downBody = src.slice(src.indexOf('const onPointerDown'), src.indexOf('const onPointerMove'));
    expect(downBody).not.toContain('setPointerCapture');
    const moveBody = src.slice(src.indexOf('const onPointerMove'), src.indexOf('const onPointerUp'));
    expect(moveBody).toContain('exceedsDragSlop');
    expect(moveBody).toContain('setPointerCapture');
  });
});
