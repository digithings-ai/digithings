/**
 * Scroll pose for the architecture tour camera.
 *
 * The walk is one 0..1 progress value. Each step owns an equal slice. The
 * camera rests on that step's boxes through the parked midpoint (where a
 * single wheel gesture settles), then glides to the next step's boxes so it
 * arrives as the narration crosses the boundary.
 */

export interface CamFrame {
  k: number;
  x: number;
  y: number;
}

export const CAM_IDENTITY: CamFrame = { k: 1, x: 0, y: 0 };

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface SpotRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

const clamp01 = (n: number): number => Math.max(0, Math.min(1, n));

const smooth = (n: number): number => {
  const t = clamp01(n);
  return t * t * (3 - 2 * t);
};

/** Active step and the 0..1 position inside it. Progress 1 stays on the last step. */
export function walkCursor(progress: number, count: number): { index: number; frac: number } {
  if (count <= 0) return { index: 0, frac: 0 };
  const v = clamp01(progress) * count;
  const index = Math.min(count - 1, Math.floor(v));
  const frac = v - index;
  return { index, frac: clamp01(frac) };
}

/**
 * 0 while the reader is parked on this step's boxes, then 0→1 across the
 * tail of the step so the camera is on the next boxes as the step index flips.
 */
export function glideAmount(frac: number): number {
  return smooth((frac - 0.55) / 0.45);
}

export function lerpCam(a: CamFrame, b: CamFrame, t: number): CamFrame {
  const u = clamp01(t);
  return {
    k: a.k + (b.k - a.k) * u,
    x: a.x + (b.x - a.x) * u,
    y: a.y + (b.y - a.y) * u,
  };
}

export function camTransform(frame: CamFrame): string {
  if (frame.k < 1.02 && Math.abs(frame.x) < 0.5 && Math.abs(frame.y) < 0.5) return "";
  return `scale(${frame.k.toFixed(4)}) translate(${frame.x.toFixed(2)}px, ${frame.y.toFixed(2)}px)`;
}

/**
 * Frame the lit boxes. Zoom is capped so a small pair of boxes cannot crop
 * the rest of the drawing out of the stage, and a step that already fills
 * the frame (the whole-graph opener) stays at identity.
 */
export function fitCamera(opts: {
  boxes: Box[];
  stageW: number;
  stageH: number;
  contentW: number;
  contentH: number;
  /** Fraction of the stage the target should occupy. */
  fill?: number;
  maxScale?: number;
  /**
   * Contain (default) fits the whole cluster in the stage, so a wide row
   * never zooms. Cover zooms on the tighter axis, up to `maxScale`, so a
   * wide short row still travels into view.
   */
  cover?: boolean;
  /** Stage pixels kept clear around the lit boxes, so the glow is never cut. */
  pad?: number;
}): CamFrame {
  const { boxes, stageW, stageH, contentW, contentH } = opts;
  const fill = opts.fill ?? 0.34;
  const maxScale = opts.maxScale ?? 1.45;
  const pad = opts.pad ?? 24;
  if (boxes.length === 0 || stageW <= 0 || stageH <= 0 || contentW <= 0 || contentH <= 0) {
    return CAM_IDENTITY;
  }
  const minX = Math.min(...boxes.map((b) => b.x));
  const minY = Math.min(...boxes.map((b) => b.y));
  const maxX = Math.max(...boxes.map((b) => b.x + b.w));
  const maxY = Math.max(...boxes.map((b) => b.y + b.h));
  const width = Math.max(maxX - minX, 1);
  const height = Math.max(maxY - minY, 1);
  /* A cluster that already covers the drawing is the whole-graph beat.
     Cover would otherwise zoom the letterboxed margin around it. */
  if (width / contentW > 0.7 && height / contentH > 0.62) return CAM_IDENTITY;
  const contain = Math.min(
    Math.max(stageW - 2 * pad, 1) / width,
    Math.max(stageH - 2 * pad, 1) / height,
  );
  const cover = Math.max(stageW / width, stageH / height);
  // Cover never crops the lit boxes: it stops at the padded contain fit.
  const zoom = opts.cover ? Math.min(fill * cover, contain) : fill * contain;
  const k = Math.max(1, Math.min(maxScale, zoom));
  if (k < 1.02) return CAM_IDENTITY;
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const pan = (span: number, content: number, centre: number): number => {
    const low = span / k - content;
    if (low > 0) return low / 2;
    return Math.min(0, Math.max(low, span / (2 * k) - centre));
  };
  return { k, x: pan(stageW, contentW, cx), y: pan(stageH, contentH, cy) };
}

/** Spotlight over the lit boxes. A union that already covers the drawing is the
    whole-graph beat — no spotlight, the full graph stays lit. */
export function unionSpot(
  boxes: Box[],
  contentW: number,
  contentH: number,
  pad = 6,
): SpotRect | null {
  if (boxes.length === 0 || contentW <= 0 || contentH <= 0) return null;
  const minX = Math.min(...boxes.map((b) => b.x));
  const minY = Math.min(...boxes.map((b) => b.y));
  const maxX = Math.max(...boxes.map((b) => b.x + b.w));
  const maxY = Math.max(...boxes.map((b) => b.y + b.h));
  const width = Math.max(maxX - minX, 0);
  const height = Math.max(maxY - minY, 0);
  if ((width * height) / (contentW * contentH) > 0.78) return null;
  return {
    left: minX - pad,
    top: minY - pad,
    width: width + pad * 2,
    height: height + pad * 2,
  };
}

export function mixSpot(
  a: SpotRect | null,
  b: SpotRect | null,
  t: number,
): { rect: SpotRect; opacity: number } | null {
  const u = clamp01(t);
  if (!a && !b) return null;
  if (!a && b) return { rect: b, opacity: u };
  if (a && !b) return { rect: a, opacity: 1 - u };
  if (!a || !b) return null;
  return {
    rect: {
      left: a.left + (b.left - a.left) * u,
      top: a.top + (b.top - a.top) * u,
      width: a.width + (b.width - a.width) * u,
      height: a.height + (b.height - a.height) * u,
    },
    opacity: 1,
  };
}
