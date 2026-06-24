'use client';

import { useCallback, useReducer, useRef } from 'react';

export interface Bbox { width: number; height: number; }
export interface Viewport { width: number; height: number; }
export interface NodeRect { x: number; y: number; width: number; height: number; }
export interface CameraTransform { x: number; y: number; scale: number; }

const MIN_SCALE = 0.4;
const MAX_SCALE = 2.5;
const PADDING = 30;

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

function clampScale(s: number): number {
  return Math.max(MIN_SCALE, Math.min(MAX_SCALE, s));
}

type Action =
  | { type: 'set'; transform: CameraTransform }
  | { type: 'pan'; dx: number; dy: number }
  | { type: 'zoom'; newScale: number; originX: number; originY: number };

function reducer(state: CameraTransform, action: Action): CameraTransform {
  switch (action.type) {
    case 'set':
      return action.transform;
    case 'pan':
      return { ...state, x: state.x + action.dx, y: state.y + action.dy };
    case 'zoom': {
      const s = clampScale(action.newScale);
      return {
        scale: s,
        x: action.originX - (action.originX - state.x) * (s / state.scale),
        y: action.originY - (action.originY - state.y) * (s / state.scale),
      };
    }
  }
}

export interface CanvasCameraResult {
  transform: CameraTransform;
  zoomIn: () => void;
  zoomOut: () => void;
  fit: (bbox: Bbox, viewport: Viewport) => void;
  centerOn: (rect: NodeRect, viewport: Viewport) => void;
  bind: {
    onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => void;
    onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => void;
    onPointerUp: () => void;
    onPointerCancel: () => void;
    onWheel: (e: React.WheelEvent<HTMLDivElement>) => void;
  };
}

export function useCanvasCamera(initialTransform?: Partial<CameraTransform>): CanvasCameraResult {
  const [transform, dispatch] = useReducer(reducer, {
    x: 20,
    y: 10,
    scale: 1,
    ...initialTransform,
  });

  const drag = useRef<{ startX: number; startY: number; startPanX: number; startPanY: number } | null>(null);
  const vpRef = useRef<HTMLDivElement | null>(null);

  // Detect prefers-reduced-motion: skip transitions (not via CSS, but DOM reads)
  const prefersReducedMotion =
    typeof window !== 'undefined'
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false;
  void prefersReducedMotion; // used by callers via CSS class on vp element

  const fit = useCallback((bbox: Bbox, viewport: Viewport) => {
    dispatch({ type: 'set', transform: computeFit(bbox, viewport) });
  }, []);

  const centerOn = useCallback((rect: NodeRect, viewport: Viewport) => {
    dispatch({ type: 'set', transform: computeCenter(rect, viewport, transform.scale) });
  }, [transform.scale]);

  const zoomIn = useCallback(() => {
    const cx = typeof window !== 'undefined' ? window.innerWidth / 2 : 400;
    const cy = typeof window !== 'undefined' ? window.innerHeight / 2 : 300;
    dispatch({ type: 'zoom', newScale: clampScale(transform.scale + 0.12), originX: cx, originY: cy });
  }, [transform.scale]);

  const zoomOut = useCallback(() => {
    const cx = typeof window !== 'undefined' ? window.innerWidth / 2 : 400;
    const cy = typeof window !== 'undefined' ? window.innerHeight / 2 : 300;
    dispatch({ type: 'zoom', newScale: clampScale(transform.scale - 0.12), originX: cx, originY: cy });
  }, [transform.scale]);

  const bind = {
    onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => {
      if ((e.target as HTMLElement).closest('[data-no-pan]')) return;
      drag.current = { startX: e.clientX, startY: e.clientY, startPanX: transform.x, startPanY: transform.y };
      (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
      vpRef.current = e.currentTarget as HTMLDivElement;
    },
    onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => {
      if (!drag.current) return;
      dispatch({
        type: 'pan',
        dx: e.clientX - drag.current.startX - (transform.x - drag.current.startPanX),
        dy: e.clientY - drag.current.startY - (transform.y - drag.current.startPanY),
      });
    },
    onPointerUp: () => { drag.current = null; },
    onPointerCancel: () => { drag.current = null; },
    onWheel: (e: React.WheelEvent<HTMLDivElement>) => {
      e.preventDefault();
      const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
      dispatch({
        type: 'zoom',
        newScale: clampScale(transform.scale - e.deltaY * 0.0013),
        originX: e.clientX - rect.left,
        originY: e.clientY - rect.top,
      });
    },
  };

  return { transform, zoomIn, zoomOut, fit, centerOn, bind };
}
