'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

export interface Bbox { width: number; height: number; }
export interface Viewport { width: number; height: number; }
export interface NodeRect { x: number; y: number; width: number; height: number; }
export interface CameraTransform { x: number; y: number; scale: number; }

const MIN_SCALE = 0.4;
const MAX_SCALE = 2.5;
const PADDING = 30;
// Pointer movement below this is a click, not a pan (see onPointerDown).
export const DRAG_SLOP_PX = 4;

/** Pure helper: has the pointer moved far enough from its down-point to count as a pan? */
export function exceedsDragSlop(startX: number, startY: number, x: number, y: number): boolean {
  return Math.hypot(x - startX, y - startY) >= DRAG_SLOP_PX;
}
// Idle window after the last wheel event before we treat the gesture as ended.
const WHEEL_IDLE_MS = 120;

/** Pure helper: compute a transform that fits `bbox` inside `viewport` (centered, scale ≤ 1). */
export function computeFit(bbox: Bbox, viewport: Viewport): CameraTransform {
  const availW = viewport.width - PADDING * 2;
  const availH = viewport.height - PADDING * 2;
  const scaleW = availW / bbox.width;
  const scaleH = availH / bbox.height;
  const scale = Math.min(1, scaleW, scaleH);
  const x = (viewport.width - bbox.width * scale) / 2;
  const y = (viewport.height - bbox.height * scale) / 2;
  return { x, y, scale };
}

/** Pure helper: compute a transform that centers `rect` within `viewport` at `scale`. */
export function computeCenter(rect: NodeRect, viewport: Viewport, scale: number): CameraTransform {
  const nodeMidX = rect.x + rect.width / 2;
  const nodeMidY = rect.y + rect.height / 2;
  const x = viewport.width / 2 - nodeMidX * scale;
  const y = viewport.height / 2 - nodeMidY * scale;
  return { x, y, scale };
}

export function clampScale(s: number): number {
  return Math.max(MIN_SCALE, Math.min(MAX_SCALE, s));
}

/**
 * Pure helper: zoom toward a viewport-relative anchor point. Keeps the world
 * point under (originX, originY) fixed while changing scale. Unit-tested.
 */
export function computeZoomToward(
  prev: CameraTransform,
  newScale: number,
  originX: number,
  originY: number,
): CameraTransform {
  const s = clampScale(newScale);
  return {
    scale: s,
    x: originX - (originX - prev.x) * (s / prev.scale),
    y: originY - (originY - prev.y) * (s / prev.scale),
  };
}

export interface CanvasCameraResult {
  /**
   * Latest committed transform. Only `scale` is guaranteed fresh on every
   * render (synced at interaction-end); x/y track the last committed value and
   * may lag the live ref mid-gesture. Use the ref + DOM for per-frame reads.
   */
  transform: CameraTransform;
  zoomIn: () => void;
  zoomOut: () => void;
  fit: (bbox: Bbox, viewport: Viewport) => void;
  centerOn: (rect: NodeRect, viewport: Viewport) => void;
  /** Attach to the scrolling/transformed layer — its DOM transform is written every frame. */
  layerRef: React.RefObject<HTMLDivElement | null>;
  /** Attach to the viewport element — the native wheel + pointer surface. */
  viewportRef: React.RefObject<HTMLDivElement | null>;
  bind: {
    onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => void;
    onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => void;
    onPointerUp: () => void;
    onPointerCancel: () => void;
  };
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false;
}

export function useCanvasCamera(initialTransform?: Partial<CameraTransform>): CanvasCameraResult {
  const initial: CameraTransform = { x: 20, y: 10, scale: 1, ...initialTransform };

  // Live transform — single source of truth, mutated synchronously per event.
  const transformRef = useRef<CameraTransform>(initial);
  // `scale` mirrored into React state so callbacks that read transform.scale
  // (zoomIn/zoomOut/centerOn) and their useCallback deps stay correct. Synced
  // on interaction-END only, never per-frame. `committed` is the last value
  // we exposed to React (used for the initial/SSR paint and consumed by callers
  // that read `transform`); it is intentionally NOT updated per pan frame.
  const [committed, setCommitted] = useState<CameraTransform>(initial);

  const layerRef = useRef<HTMLDivElement | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);

  const drag = useRef<{
    startX: number;
    startY: number;
    startPanX: number;
    startPanY: number;
    pointerId: number;
    captured: boolean;
  } | null>(null);
  const rafId = useRef<number | null>(null);
  const isInteracting = useRef<boolean>(false);
  const wheelIdleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---- DOM writes -------------------------------------------------------

  const writeTransform = useCallback(() => {
    rafId.current = null;
    const el = layerRef.current;
    if (!el) return;
    const { x, y, scale } = transformRef.current;
    el.style.transform = `translate3d(${x}px,${y}px,0) scale(${scale})`;
  }, []);

  // Coalesce all transform writes into one rAF per frame.
  const scheduleWrite = useCallback(() => {
    if (rafId.current !== null) return;
    rafId.current = requestAnimationFrame(writeTransform);
  }, [writeTransform]);

  const setTransitionEnabled = useCallback((enabled: boolean) => {
    const el = layerRef.current;
    if (!el) return;
    el.style.transition = enabled && !prefersReducedMotion() ? 'transform 150ms ease-out' : 'none';
  }, []);

  // Begin a direct-manipulation gesture: kill the CSS transition so the layer
  // tracks the pointer/wheel exactly instead of tweening (rubber-banding).
  const beginInteraction = useCallback(() => {
    if (isInteracting.current) return;
    isInteracting.current = true;
    setTransitionEnabled(false);
  }, [setTransitionEnabled]);

  // End a gesture: re-enable the transition for subsequent programmatic moves
  // and sync the committed scale into React state.
  const endInteraction = useCallback(() => {
    if (!isInteracting.current) return;
    isInteracting.current = false;
    setTransitionEnabled(true);
    setCommitted({ ...transformRef.current });
  }, [setTransitionEnabled]);

  // ---- Imperative camera moves (programmatic → keep transition) ---------

  const applyProgrammatic = useCallback(
    (next: CameraTransform) => {
      transformRef.current = next;
      setTransitionEnabled(true);
      scheduleWrite();
      setCommitted({ ...next });
    },
    [scheduleWrite, setTransitionEnabled],
  );

  const fit = useCallback(
    (bbox: Bbox, viewport: Viewport) => {
      applyProgrammatic(computeFit(bbox, viewport));
    },
    [applyProgrammatic],
  );

  const centerOn = useCallback(
    (rect: NodeRect, viewport: Viewport) => {
      applyProgrammatic(computeCenter(rect, viewport, transformRef.current.scale));
    },
    [applyProgrammatic],
  );

  const zoomByButton = useCallback(
    (delta: number) => {
      const vp = viewportRef.current;
      let originX = 400;
      let originY = 300;
      if (vp) {
        const rect = vp.getBoundingClientRect();
        originX = rect.width / 2;
        originY = rect.height / 2;
      }
      const next = computeZoomToward(
        transformRef.current,
        clampScale(transformRef.current.scale + delta),
        originX,
        originY,
      );
      applyProgrammatic(next);
    },
    [applyProgrammatic],
  );

  const zoomIn = useCallback(() => zoomByButton(0.12), [zoomByButton]);
  const zoomOut = useCallback(() => zoomByButton(-0.12), [zoomByButton]);

  // ---- Pointer pan ------------------------------------------------------

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if ((e.target as HTMLElement).closest('[data-no-pan]')) return;
      // Record the candidate pan but do NOT capture the pointer yet: capturing
      // on pointerdown retargets the subsequent `click` to the viewport, which
      // silently swallowed every node click on the canvas (#1553 — documents
      // could only be opened via keyboard). Capture happens in onPointerMove
      // once the gesture exceeds the drag slop, so stationary clicks reach
      // the nodes and real drags still pan.
      drag.current = {
        startX: e.clientX,
        startY: e.clientY,
        startPanX: transformRef.current.x,
        startPanY: transformRef.current.y,
        pointerId: e.pointerId,
        captured: false,
      };
    },
    [],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const d = drag.current;
      if (!d) return;
      if (!d.captured) {
        // Drag slop: treat sub-slop movement as a click-in-progress, not a pan.
        if (!exceedsDragSlop(d.startX, d.startY, e.clientX, e.clientY)) return;
        d.captured = true;
        (e.currentTarget as HTMLDivElement).setPointerCapture(d.pointerId);
        beginInteraction();
      }
      // Set transform absolutely from start + delta — no accumulation, no
      // stale-closure wobble.
      transformRef.current = {
        ...transformRef.current,
        x: d.startPanX + (e.clientX - d.startX),
        y: d.startPanY + (e.clientY - d.startY),
      };
      scheduleWrite();
    },
    [beginInteraction, scheduleWrite],
  );

  const onPointerUp = useCallback(() => {
    drag.current = null;
    endInteraction();
  }, [endInteraction]);

  const onPointerCancel = useCallback(() => {
    drag.current = null;
    endInteraction();
  }, [endInteraction]);

  // Stable bind object so the spread onto the viewport keeps handler identity.
  const bind = useMemo(
    () => ({ onPointerDown, onPointerMove, onPointerUp, onPointerCancel }),
    [onPointerDown, onPointerMove, onPointerUp, onPointerCancel],
  );

  // ---- Native wheel (passive:false so preventDefault cancels page zoom) --

  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp) return;

    const handleWheel = (e: WheelEvent) => {
      // Normalize deltaMode: line (1) and page (2) → pixels.
      const factor = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? window.innerHeight : 1;
      const dx = e.deltaX * factor;
      const dy = e.deltaY * factor;

      beginInteraction();

      if (e.ctrlKey) {
        // Trackpad pinch (macOS surfaces it as ctrl+wheel; native default is
        // page zoom — preventDefault here, coupled with passive:false).
        e.preventDefault();
        const rect = vp.getBoundingClientRect();
        const originX = e.clientX - rect.left;
        const originY = e.clientY - rect.top;
        const newScale = clampScale(transformRef.current.scale * Math.exp(-dy * 0.0015));
        transformRef.current = computeZoomToward(
          transformRef.current,
          newScale,
          originX,
          originY,
        );
      } else {
        // Two-finger scroll → pan.
        e.preventDefault();
        transformRef.current = {
          ...transformRef.current,
          x: transformRef.current.x - dx,
          y: transformRef.current.y - dy,
        };
      }

      scheduleWrite();

      // Debounced wheel-idle → treat the gesture as ended.
      if (wheelIdleTimer.current) clearTimeout(wheelIdleTimer.current);
      wheelIdleTimer.current = setTimeout(() => {
        wheelIdleTimer.current = null;
        endInteraction();
      }, WHEEL_IDLE_MS);
    };

    vp.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      // Clean re-subscribe under React 19 StrictMode double-invoke.
      vp.removeEventListener('wheel', handleWheel);
    };
  }, [beginInteraction, endInteraction, scheduleWrite]);

  // Write the initial transform once the layer node mounts, and set the
  // baseline transition state.
  useEffect(() => {
    setTransitionEnabled(true);
    scheduleWrite();
    return () => {
      if (rafId.current !== null) {
        cancelAnimationFrame(rafId.current);
        rafId.current = null;
      }
      if (wheelIdleTimer.current) {
        clearTimeout(wheelIdleTimer.current);
        wheelIdleTimer.current = null;
      }
    };
  }, [scheduleWrite, setTransitionEnabled]);

  return {
    transform: committed,
    zoomIn,
    zoomOut,
    fit,
    centerOn,
    layerRef,
    viewportRef,
    bind,
  };
}
