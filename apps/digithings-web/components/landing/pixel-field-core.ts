/**
 * Cube-field engine for the welcome hero: the DPR-aware grid, the square-cell
 * renderer, the resize/intersection/reduced-motion/theme-change lifecycle, and
 * the mouse trail. It knows nothing about what is drawn; a `Subject` decides
 * which cells light up and why (see `embedding-map.ts`).
 *
 * The trail is monochrome ink, not a cycling hue. digithings.ai collapses its
 * accent to monochrome ink/white by design (see globals.css, "Neutral platform
 * palette").
 */

export type Grid = {
  cols: number;
  rows: number;
  pitch: number;
  width: number;
  height: number;
  offsetX: number;
  offsetY: number;
  small: boolean;
};

export type FieldState = {
  target: Float32Array;
  kind: Uint8Array;
};

export type Subject = {
  update(time: number, state: FieldState): void;
};

export function hash(a: number, b: number): number {
  let n = (Math.imul(0x165667b1, a) + Math.imul(0x27d4eb2f, b)) | 0;
  n = Math.imul(n ^ (n >>> 13), 0x4bf19f61);
  return ((n ^ (n >>> 16)) >>> 0) / 0x100000000;
}

export function cellPoint(grid: Grid, index: number): { x: number; y: number } {
  const col = index % grid.cols;
  const row = (index - col) / grid.cols;
  return {
    x: grid.offsetX + (col + 0.5) * grid.pitch,
    y: grid.offsetY + (row + 0.5) * grid.pitch,
  };
}

export function cellAt(grid: Grid, x: number, y: number): number {
  const col = Math.floor((x - grid.offsetX) / grid.pitch);
  const row = Math.floor((y - grid.offsetY) / grid.pitch);
  if (col < 0 || row < 0 || col >= grid.cols || row >= grid.rows) return -1;
  return row * grid.cols + col;
}

export function paintMax(state: FieldState, index: number, alpha: number, kind: number): void {
  if (index < 0 || index >= state.target.length) return;
  if (alpha >= (state.target[index] ?? 0)) {
    state.target[index] = alpha;
    state.kind[index] = kind;
  }
}

function parseColor(value: string, fallback: [number, number, number]): [number, number, number] {
  const hex = value.trim().match(/^#([0-9a-f]{6})$/i);
  if (hex?.[1]) {
    const n = Number.parseInt(hex[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const rgb = value.trim().match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i);
  return rgb ? [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])] : fallback;
}

function colorsOf(el: HTMLElement): { foreground: [number, number, number]; accent: [number, number, number] } {
  const style = getComputedStyle(el);
  return {
    foreground: parseColor(style.color, [20, 24, 27]),
    accent: parseColor(style.accentColor, [12, 124, 113]),
  };
}

export function mountField(canvas: HTMLCanvasElement, makeSubject: (grid: Grid) => Subject): () => void {
  const context = canvas.getContext("2d");
  const parent = canvas.parentElement;
  if (!context || !parent) return () => {};
  const ctx: CanvasRenderingContext2D = context;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let colors = colorsOf(canvas);
  let cols = 0;
  let rows = 0;
  let size = 8;
  let pitch = 12;
  let ox = 0;
  let oy = 0;
  let target = new Float32Array();
  let display = new Float32Array();
  let kind = new Uint8Array();
  let trail = new Float32Array();
  let reveal = new Float32Array();
  let subject: Subject = makeSubject({ cols: 1, rows: 1, pitch: 12, width: 1, height: 1, offsetX: 0, offsetY: 0, small: false });
  let born = 0;
  let raf = 0;
  let visible = true;

  function layout(first: boolean) {
    const ratio = devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const small = width < 640;
    size = small ? 5 : 8;
    pitch = small ? 8 : 12;
    cols = Math.ceil(width / pitch);
    rows = Math.floor(height / pitch);
    ox = (width - cols * pitch) / 2;
    oy = height - rows * pitch;
    const count = cols * rows;
    target = new Float32Array(count);
    display = new Float32Array(count);
    kind = new Uint8Array(count);
    trail = new Float32Array(count);
    reveal = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const col = i % cols;
      reveal[i] = first ? ((col + 0.5) / cols) * 900 + 300 * Math.random() : 0;
    }
    const grid: Grid = { cols, rows, pitch, width, height, offsetX: ox, offsetY: oy, small };
    subject = makeSubject(grid);
    subject.update(performance.now(), { target, kind });
    if (reduced || !first) display.set(target);
    born = performance.now();
  }

  function square(index: number) {
    const col = index % cols;
    const row = (index - col) / cols;
    const pad = (pitch - size) / 2;
    ctx.fillRect(ox + col * pitch + pad, oy + row * pitch + pad, size, size);
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
    for (const accent of [0, 1]) {
      const [r, g, b] = accent ? colors.accent : colors.foreground;
      ctx.fillStyle = `rgb(${r},${g},${b})`;
      for (let i = 0; i < display.length; i++) {
        if ((trail[i] ?? 0) > 0.02 || (kind[i] ?? 0) !== accent) continue;
        const alpha = display[i] ?? 0;
        if (alpha < 0.01) continue;
        ctx.globalAlpha = Math.min(1, alpha);
        square(i);
      }
    }
    // Trail: monochrome ink only — no hue cycling. A brighter, more opaque
    // version of the same foreground color the field itself uses.
    const [r, g, b] = colors.foreground;
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    for (let i = 0; i < trail.length; i++) {
      const alpha = trail[i] ?? 0;
      if (alpha <= 0.02) continue;
      ctx.globalAlpha = Math.min(1, alpha);
      square(i);
    }
    ctx.globalAlpha = 1;
  }

  function tick(now: number) {
    const elapsed = now - born;
    subject.update(now, { target, kind });
    for (let i = 0; i < display.length; i++) {
      const goal = elapsed < (reveal[i] ?? 0) ? 0 : (target[i] ?? 0);
      display[i] += (goal - display[i]) * 0.18;
      const next = (trail[i] ?? 0) * 0.94;
      trail[i] = next < 0.02 ? 0 : next;
    }
    draw();
    raf = visible ? requestAnimationFrame(tick) : 0;
  }

  function onPointer(event: PointerEvent) {
    if (event.pointerType !== "mouse") return;
    const rect = canvas.getBoundingClientRect();
    const col = Math.floor((event.clientX - rect.left - ox) / pitch);
    const row = Math.floor((event.clientY - rect.top - oy) / pitch);
    for (let n = 0; n < 3; n++) {
      const c = col + Math.round((Math.random() - 0.5) * 5);
      const r = row + Math.round((Math.random() - 0.5) * 5);
      if (c < 0 || r < 0 || c >= cols || r >= rows) continue;
      const i = r * cols + c;
      const alpha = n === 0 ? 0.9 : 0.5;
      trail[i] = Math.max(trail[i] ?? 0, alpha);
    }
  }

  layout(true);
  if (reduced) draw();
  else raf = requestAnimationFrame(tick);
  parent.addEventListener("pointermove", onPointer);

  let sizeKey = `${canvas.clientWidth}x${canvas.clientHeight}`;
  const resize = new ResizeObserver(() => {
    const next = `${canvas.clientWidth}x${canvas.clientHeight}`;
    if (next === sizeKey) return;
    sizeKey = next;
    layout(false);
    if (reduced) draw();
  });
  resize.observe(canvas);

  const seen = new IntersectionObserver(([entry]) => {
    visible = entry?.isIntersecting ?? true;
    if (visible && !raf && !reduced) raf = requestAnimationFrame(tick);
  });
  seen.observe(canvas);

  const refreshColors = () => {
    colors = colorsOf(canvas);
    if (reduced) draw();
  };
  const scheme = matchMedia("(prefers-color-scheme: dark)");
  scheme.addEventListener("change", refreshColors);
  const theme = new MutationObserver(refreshColors);
  theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  return () => {
    if (raf) cancelAnimationFrame(raf);
    parent.removeEventListener("pointermove", onPointer);
    resize.disconnect();
    seen.disconnect();
    scheme.removeEventListener("change", refreshColors);
    theme.disconnect();
  };
}
