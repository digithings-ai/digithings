import { LAND } from "./pixel-land";

/**
 * The welcome pixel field: a land-mask grid, exchange hubs that pulse and
 * arc, and a short colored trail under the mouse. Ported from the gloom
 * hero the owner picked on :3903.
 */

const CITIES = [
  { lat: 40.7, lon: -74, timeZone: "America/New_York", open: 9.5, close: 16 },
  { lat: 43.7, lon: -79.4, timeZone: "America/Toronto", open: 9.5, close: 16 },
  { lat: 19.4, lon: -99.1, timeZone: "America/Mexico_City", open: 8.5, close: 15 },
  { lat: -23.5, lon: -46.6, timeZone: "America/Sao_Paulo", open: 10, close: 17 },
  { lat: 51.5, lon: -0.1, timeZone: "Europe/London", open: 8, close: 16.5 },
  { lat: 50.1, lon: 8.7, timeZone: "Europe/Berlin", open: 9, close: 17.5 },
  { lat: 47.4, lon: 8.5, timeZone: "Europe/Zurich", open: 9, close: 17.5 },
  { lat: -26.2, lon: 28, timeZone: "Africa/Johannesburg", open: 9, close: 17 },
  { lat: 19.1, lon: 72.9, timeZone: "Asia/Kolkata", open: 9.25, close: 15.5 },
  { lat: 1.3, lon: 103.9, timeZone: "Asia/Singapore", open: 9, close: 17 },
  { lat: 22.3, lon: 114.2, timeZone: "Asia/Hong_Kong", open: 9.5, close: 16 },
  { lat: 31.2, lon: 121.5, timeZone: "Asia/Shanghai", open: 9.5, close: 15 },
  { lat: 37.6, lon: 127, timeZone: "Asia/Seoul", open: 9, close: 15.5 },
  { lat: 35.7, lon: 139.8, timeZone: "Asia/Tokyo", open: 9, close: 15.5 },
  { lat: -33.9, lon: 151.2, timeZone: "Australia/Sydney", open: 10, close: 16 },
] as const;

const WEEKDAYS = new Set(["Mon", "Tue", "Wed", "Thu", "Fri"]);
const DEG = Math.PI / 180;

type Grid = {
  cols: number;
  rows: number;
  pitch: number;
  width: number;
  height: number;
  offsetX: number;
  offsetY: number;
  small: boolean;
};

type FieldState = {
  target: Float32Array;
  kind: Uint8Array;
};

function hash(a: number, b: number): number {
  let n = (Math.imul(0x165667b1, a) + Math.imul(0x27d4eb2f, b)) | 0;
  n = Math.imul(n ^ (n >>> 13), 0x4bf19f61);
  return ((n ^ (n >>> 16)) >>> 0) / 0x100000000;
}

function cellPoint(grid: Grid, index: number): { x: number; y: number } {
  const col = index % grid.cols;
  const row = (index - col) / grid.cols;
  return {
    x: grid.offsetX + (col + 0.5) * grid.pitch,
    y: grid.offsetY + (row + 0.5) * grid.pitch,
  };
}

function cellAt(grid: Grid, x: number, y: number): number {
  const col = Math.floor((x - grid.offsetX) / grid.pitch);
  const row = Math.floor((y - grid.offsetY) / grid.pitch);
  if (col < 0 || row < 0 || col >= grid.cols || row >= grid.rows) return -1;
  return row * grid.cols + col;
}

function land(lon: number, lat: number): boolean {
  const row = Math.floor((90 - lat) / 2);
  const col = Math.floor(((((lon + 180) % 360) + 360) % 360) / 2);
  if (row < 0 || row >= 90) return false;
  const bit = 180 * row + col;
  return (((LAND[bit >> 3] ?? 0) >> (7 - (bit & 7))) & 1) === 1;
}

function solarLon(): number {
  const now = new Date();
  return (12 - now.getUTCHours() - now.getUTCMinutes() / 60) * 15;
}

function marketOpen(city: (typeof CITIES)[number], now: Date): boolean {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: city.timeZone,
    weekday: "short",
    hour: "numeric",
    minute: "numeric",
    hourCycle: "h23",
  }).formatToParts(now);
  const part = (type: string) => parts.find((item) => item.type === type)?.value;
  if (!WEEKDAYS.has(part("weekday") ?? "")) return false;
  const hour = Number(part("hour")) + Number(part("minute")) / 60;
  return hour >= city.open && hour < city.close;
}

function paintMax(state: FieldState, index: number, alpha: number, kind: number): void {
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

function colorsOf(el: HTMLElement): {
  foreground: [number, number, number];
  accent: [number, number, number];
} {
  const style = getComputedStyle(el);
  return {
    foreground: parseColor(style.color, [20, 24, 27]),
    accent: parseColor(style.accentColor, [12, 124, 113]),
  };
}

function createWorld(grid: Grid) {
  const wide = grid.width / grid.height >= 2;
  const scale = wide ? 360 / grid.width : 130 / grid.height;
  const origin = wide ? 10 : -new Date().getTimezoneOffset() / 60 * 15;
  const count = grid.cols * grid.rows;
  const vignette = new Float32Array(count);
  const cx = grid.width / 2;
  const cy = grid.height * 0.46;
  const rx = grid.width * (grid.small ? 0.62 : 0.34);
  const ry = grid.height * 0.5;
  for (let i = 0; i < count; i++) {
    const p = cellPoint(grid, i);
    const t = Math.min(1, Math.max(0, (Math.hypot((p.x - cx) / rx, (p.y - cy) / ry) - 0.7) / 0.55));
    vignette[i] = 0.08 + 0.92 * t * t * (3 - 2 * t);
  }
  const isLand = new Uint8Array(count);
  const lit = new Uint8Array(count);
  const flicker = new Float32Array(count);
  const lonOf = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    const p = cellPoint(grid, i);
    const lon = origin + (p.x - grid.width / 2) * scale;
    const lat = 12 - (p.y - grid.height / 2) * scale;
    lonOf[i] = lon;
    isLand[i] = land(lon, lat) ? 1 : 0;
    lit[i] = isLand[i] && Math.random() < 0.55 ? 1 : 0;
    flicker[i] = 0.6 + 0.4 * Math.random();
  }
  const hubs = CITIES.map((city, index) => {
    const lon = ((city.lon - origin + 180) % 360 + 360) % 360 - 180;
    return {
      point: {
        x: grid.width / 2 + lon / scale,
        y: grid.height / 2 - (city.lat - 12) / scale,
      },
      period: 3200 + 3400 * hash(index, 7),
      phase: 6000 * hash(index, 3),
    };
  });
  const ring = Math.max(48, 7 * grid.pitch);
  let openCache: boolean[] = [];
  let openAt = -Infinity;
  const openNow = (time: number) => {
    if (time - openAt > 60000) {
      openAt = time;
      const now = new Date();
      openCache = CITIES.map((city) => marketOpen(city, now));
    }
    return openCache;
  };
  let sun = solarLon();
  let sunAt = 0;
  const arcs: { from: number; to: number; start: number; duration: number }[] = [];
  let nextArc = 2000;
  return {
    update(time: number, state: FieldState) {
      const open = openNow(time);
      if (time - sunAt > 60000) {
        sunAt = time;
        sun = solarLon();
      }
      const flips = Math.max(1, Math.round(0.006 * count));
      for (let n = 0; n < flips; n++) {
        const i = Math.floor(Math.random() * count);
        lit[i] = isLand[i] && Math.random() < 0.55 ? 1 : 0;
      }
      for (let i = 0; i < count; i++) {
        state.kind[i] = 0;
        if (!lit[i]) {
          state.target[i] = 0;
          continue;
        }
        const day = Math.cos((lonOf[i] - sun) * DEG) > 0 ? 1.2 : 0.8;
        state.target[i] = 0.09 * day * flicker[i] * (vignette[i] ?? 0);
      }
      const reach = Math.ceil(ring / grid.pitch) + 1;
      hubs.forEach((hub, index) => {
        const phase = (time + hub.phase) % hub.period;
        if (phase > 1700) return;
        const t = phase / 1700;
        const radius = t * ring;
        const live = open[index] === true;
        const alpha = (1 - t) * (live ? 0.5 : 0.26);
        const center = cellAt(grid, hub.point.x, hub.point.y);
        if (center < 0) return;
        const col = center % grid.cols;
        const row = (center - col) / grid.cols;
        for (let dy = -reach; dy <= reach; dy++) {
          for (let dx = -reach; dx <= reach; dx++) {
            const c = col + dx;
            const r = row + dy;
            if (c < 0 || r < 0 || c >= grid.cols || r >= grid.rows) continue;
            const i = r * grid.cols + c;
            const p = cellPoint(grid, i);
            if (Math.abs(Math.hypot(p.x - hub.point.x, p.y - hub.point.y) - radius) > 0.6 * grid.pitch) {
              continue;
            }
            paintMax(state, i, alpha * (vignette[i] ?? 0), live ? 1 : 0);
          }
        }
      });
      hubs.forEach((hub, index) => {
        const i = cellAt(grid, hub.point.x, hub.point.y);
        if (i < 0) return;
        const live = open[index] === true;
        const pulse = 0.5 + 0.5 * Math.sin(((time + hub.phase) / 2400) * Math.PI * 2);
        paintMax(state, i, (live ? 0.45 + 0.3 * pulse : 0.22) * (vignette[i] ?? 0), live ? 1 : 0);
      });
      if (time > nextArc && arcs.length < 2) {
        const from = Math.floor(Math.random() * hubs.length);
        let to = from;
        while (to === from) to = Math.floor(Math.random() * hubs.length);
        const a = hubs[from].point;
        const b = hubs[to].point;
        const dist = Math.hypot(b.x - a.x, b.y - a.y);
        arcs.push({ from, to, start: time, duration: 1100 + 2.6 * dist });
        nextArc = time + 1600 + 2400 * Math.random();
      }
      for (let n = arcs.length - 1; n >= 0; n--) {
        const arc = arcs[n];
        const a = hubs[arc.from]?.point;
        const b = hubs[arc.to]?.point;
        if (!a || !b) {
          arcs.splice(n, 1);
          continue;
        }
        const t = (time - arc.start) / arc.duration;
        if (t > 1.25) {
          arcs.splice(n, 1);
          continue;
        }
        const lift = 0.3 * Math.hypot(b.x - a.x, b.y - a.y);
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2 - lift;
        for (let step = 0; step < 8; step++) {
          const u = Math.min(1, t - 0.03 * step);
          if (u < 0) continue;
          const x = (1 - u) ** 2 * a.x + 2 * (1 - u) * u * mx + u ** 2 * b.x;
          const y = (1 - u) ** 2 * a.y + 2 * (1 - u) * u * my + u ** 2 * b.y;
          const i = cellAt(grid, x, y);
          if (i >= 0) paintMax(state, i, 0.5 * (1 - step / 8) * (vignette[i] ?? 0), 1);
        }
      }
    },
  };
}

export function mountPixelField(canvas: HTMLCanvasElement): () => void {
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
  let trailHue = new Float32Array();
  let reveal = new Float32Array();
  let hue = 155;
  let lastPointer: { x: number; y: number } | null = null;
  let world = createWorld({
    cols: 1,
    rows: 1,
    pitch: 12,
    width: 1,
    height: 1,
    offsetX: 0,
    offsetY: 0,
    small: false,
  });
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
    trailHue = new Float32Array(count);
    reveal = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const col = i % cols;
      reveal[i] = first ? ((col + 0.5) / cols) * 900 + 300 * Math.random() : 0;
    }
    const grid: Grid = { cols, rows, pitch, width, height, offsetX: ox, offsetY: oy, small };
    world = createWorld(grid);
    world.update(performance.now(), { target, kind });
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
    const [r, g, b] = colors.foreground;
    const light = r + g + b > 382 ? 64 : 52;
    for (let i = 0; i < trail.length; i++) {
      const alpha = trail[i] ?? 0;
      if (alpha <= 0.02) continue;
      ctx.fillStyle = `hsl(${trailHue[i] ?? 0} 85% ${light}%)`;
      ctx.globalAlpha = Math.min(1, alpha);
      square(i);
    }
    ctx.globalAlpha = 1;
  }

  function tick(now: number) {
    const elapsed = now - born;
    world.update(now, { target, kind });
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
    if (lastPointer) {
      hue = (hue + Math.hypot(event.clientX - lastPointer.x, event.clientY - lastPointer.y) * 0.4) % 360;
    }
    lastPointer = { x: event.clientX, y: event.clientY };
    const rect = canvas.getBoundingClientRect();
    const col = Math.floor((event.clientX - rect.left - ox) / pitch);
    const row = Math.floor((event.clientY - rect.top - oy) / pitch);
    for (let n = 0; n < 3; n++) {
      const c = col + Math.round((Math.random() - 0.5) * 5);
      const r = row + Math.round((Math.random() - 0.5) * 5);
      if (c < 0 || r < 0 || c >= cols || r >= rows) continue;
      const i = r * cols + c;
      const alpha = n === 0 ? 0.9 : 0.5;
      if (alpha >= (trail[i] ?? 0)) trailHue[i] = hue;
      trail[i] = Math.max(trail[i] ?? 0, alpha);
    }
  }

  function onLeave() {
    lastPointer = null;
  }

  layout(true);
  if (reduced) draw();
  else raf = requestAnimationFrame(tick);
  parent.addEventListener("pointermove", onPointer);
  parent.addEventListener("pointerleave", onLeave);

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
    parent.removeEventListener("pointerleave", onLeave);
    resize.disconnect();
    seen.disconnect();
    scheme.removeEventListener("change", refreshColors);
    theme.disconnect();
  };
}
