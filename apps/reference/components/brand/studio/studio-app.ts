/**
 * Imperative engine for the brand studio composer.
 *
 * The studio is a single-purpose tool: a canvas, a fixed inspector and a
 * preset gallery. Keeping the engine imperative lets the stage behave exactly
 * like the standalone builder it came from (pixel SVG injection, CSS-driven
 * animation, synchronous centring) while React owns the page shell.
 */

type Theme = { bg: string; ink: string; accent: string };
type Palettes = Record<string, { dark: Theme; light: Theme }>;
type LayerSettings = { show: boolean; size: number; x?: number; y?: number };
type PresetSettings = {
  width: number;
  height: number;
  background: string;
  theme: string;
  mode: "dark" | "light";
  layout: string;
  logo: LayerSettings;
  wordmark: LayerSettings;
  animated: boolean;
  center?: boolean;
};
type Preset = { id: string; label: string; group: string; settings: PresetSettings };
type PresetsFile = { version: number; system: string; presets: Preset[] };
type FieldData = { inner: string; fw: number; fh: number };

const ASSET_ROOT = "/brand/studio";
const ANIM_CLASSES = ["anim-build", "anim-idle", "anim-glint", "anim-strays"] as const;
const FIELD_ASPECTS: Record<string, number> = {
  x: 3,
  "linkedin-personal": 4,
  "linkedin-company": 5.9,
  og: 1.9,
  square: 1,
  story: 0.5625,
};
const LAYOUTS: Record<string, { logo: Required<LayerSettings>; word: Required<LayerSettings> }> = {
  "logo-left": {
    logo: { show: true, size: 36, x: 30, y: 50 },
    word: { show: true, size: 20, x: 66, y: 50 },
  },
  stacked: {
    logo: { show: true, size: 30, x: 50, y: 38 },
    word: { show: true, size: 13, x: 50, y: 68 },
  },
  "logo-only": {
    logo: { show: true, size: 60, x: 50, y: 50 },
    word: { show: false, size: 10, x: 50, y: 50 },
  },
  "word-only": {
    logo: { show: false, size: 10, x: 50, y: 50 },
    word: { show: true, size: 30, x: 50, y: 50 },
  },
  "logo-right": {
    logo: { show: true, size: 36, x: 70, y: 50 },
    word: { show: true, size: 20, x: 34, y: 50 },
  },
};

function must<T extends HTMLElement>(root: ParentNode, selector: string): T {
  const element = root.querySelector<T>(selector);
  if (!element) throw new Error(`brand studio: missing ${selector}`);
  return element;
}

function queryAll<T extends Element>(root: ParentNode, selector: string): T[] {
  return Array.from(root.querySelectorAll<T>(selector));
}

function escapeXml(value: string): string {
  return String(value).replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" })[char] ?? char,
  );
}

async function getText(url: string, signal: AbortSignal): Promise<string> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`${url} → ${response.status}`);
  return response.text();
}

async function getJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`${url} → ${response.status}`);
  return (await response.json()) as T;
}

function parseColor(value: string): [number, number, number] {
  const color = (value || "").trim();
  if (color[0] === "#") {
    let hex = color.slice(1);
    if (hex.length === 3) {
      hex = hex
        .split("")
        .map((part) => part + part)
        .join("");
    }
    if (hex.length === 6 || hex.length === 8) {
      return [
        parseInt(hex.slice(0, 2), 16),
        parseInt(hex.slice(2, 4), 16),
        parseInt(hex.slice(4, 6), 16),
      ];
    }
  }
  const match = color.match(/rgba?\(([^)]+)\)/);
  if (match) {
    const parts = match[1].split(/[\s,/]+/).map(Number);
    return [parts[0] || 0, parts[1] || 0, parts[2] || 0];
  }
  return [0, 0, 0];
}

function mix(a: string, b: string, weight: number): string {
  const A = parseColor(a);
  const B = parseColor(b);
  return `rgb(${Math.round(A[0] * weight + B[0] * (1 - weight))}, ${Math.round(
    A[1] * weight + B[1] * (1 - weight),
  )}, ${Math.round(A[2] * weight + B[2] * (1 - weight))})`;
}

function round(value: number): number {
  return Number(value.toFixed(4));
}

export function initBrandStudio(root: HTMLElement): () => void {
  const controller = new AbortController();
  const { signal } = controller;
  let disposed = false;
  let toastTimer: ReturnType<typeof setTimeout> | undefined;
  let fitFrame = 0;

  const stage = must<HTMLDivElement>(root, "#bs-stage");
  const bg = must<HTMLDivElement>(root, "#bs-bg");
  const logoLayer = must<HTMLDivElement>(root, "#bs-logoLayer");
  const wordLayer = must<HTMLDivElement>(root, "#bs-wordLayer");
  const presetSel = must<HTMLSelectElement>(root, "#bs-presetSel");
  const cw = must<HTMLInputElement>(root, "#bs-cw");
  const ch = must<HTMLInputElement>(root, "#bs-ch");
  const bgmode = must<HTMLSelectElement>(root, "#bs-bgmode");
  const themeSel = must<HTMLSelectElement>(root, "#bs-theme");
  const pol = must<HTMLSelectElement>(root, "#bs-pol");
  const layoutSel = must<HTMLSelectElement>(root, "#bs-layout");
  const logoOn = must<HTMLInputElement>(root, "#bs-logoOn");
  const logoS = must<HTMLInputElement>(root, "#bs-logoS");
  const logoX = must<HTMLInputElement>(root, "#bs-logoX");
  const logoY = must<HTMLInputElement>(root, "#bs-logoY");
  const wordOn = must<HTMLInputElement>(root, "#bs-wordOn");
  const wordS = must<HTMLInputElement>(root, "#bs-wordS");
  const wordX = must<HTMLInputElement>(root, "#bs-wordX");
  const wordY = must<HTMLInputElement>(root, "#bs-wordY");
  const animOn = must<HTMLInputElement>(root, "#bs-animOn");
  const replay = must<HTMLButtonElement>(root, "#bs-replay");
  const centerBtn = must<HTMLButtonElement>(root, "#bs-center");
  const canvasArea = must<HTMLDivElement>(root, "#bs-canvasArea");
  const canvasTitle = must<HTMLHeadingElement>(root, "#bs-canvasTitle");
  const canvasDims = must<HTMLSpanElement>(root, "#bs-canvasDims");
  const canvasTheme = must<HTMLSpanElement>(root, "#bs-canvasTheme");
  const dirtyBadge = must<HTMLSpanElement>(root, "#bs-dirtyBadge");
  const resetPreset = must<HTMLButtonElement>(root, "#bs-resetPreset");
  const presetHint = must<HTMLParagraphElement>(root, "#bs-presetHint");
  const pngScale = must<HTMLSelectElement>(root, "#bs-pngScale");
  const exportPngBtn = must<HTMLButtonElement>(root, "#bs-exportPng");
  const exportSvgBtn = must<HTMLButtonElement>(root, "#bs-exportSvg");
  const toastEl = must<HTMLDivElement>(root, "#bs-toast");
  const gallery = must<HTMLDivElement>(root, "#bs-presetGallery");
  const galleryCount = must<HTMLSpanElement>(root, "#bs-galleryCount");
  const logoBody = must<HTMLDivElement>(root, "#bs-logoBody");
  const wordBody = must<HTMLDivElement>(root, "#bs-wordBody");
  const lsv = must<HTMLOutputElement>(root, "#bs-lsv");
  const lxv = must<HTMLOutputElement>(root, "#bs-lxv");
  const lyv = must<HTMLOutputElement>(root, "#bs-lyv");
  const wsv = must<HTMLOutputElement>(root, "#bs-wsv");
  const wxv = must<HTMLOutputElement>(root, "#bs-wxv");
  const wyv = must<HTMLOutputElement>(root, "#bs-wyv");

  const state = { presetId: "", dirty: false, exporting: false };
  let presets: PresetsFile = { version: 0, system: "", presets: [] };
  let palettes: Palettes = {};
  let logoCache = { key: "", value: "" };
  let wordCache = { key: "", value: "" };
  const fieldCache = new Map<string, FieldData>();

  const dims = () => ({
    w: Math.max(16, Math.min(8192, Math.round(Number(cw.value) || 1500))),
    h: Math.max(16, Math.min(8192, Math.round(Number(ch.value) || 500))),
  });

  const fieldKey = (w: number, h: number): string => {
    const aspect = w / h;
    let best = "x";
    let bestDistance = Number.POSITIVE_INFINITY;
    for (const [key, target] of Object.entries(FIELD_ASPECTS)) {
      const distance = Math.abs(Math.log(aspect / target));
      if (distance < bestDistance) {
        bestDistance = distance;
        best = key;
      }
    }
    return best;
  };

  const layoutValues = (layout: string) => LAYOUTS[layout] ?? LAYOUTS["logo-left"];

  const syncModeSeg = () => {
    queryAll<HTMLButtonElement>(root, "#bs-modeSeg button").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.mode === pol.value));
    });
  };

  const syncBgSeg = () => {
    queryAll<HTMLButtonElement>(root, "#bs-bgSeg button").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.bg === bgmode.value));
    });
  };

  const syncThemeLabel = () => {
    const name = themeSel.value === "default" ? "Default" : themeSel.value;
    canvasTheme.textContent = `${name} · ${pol.value === "dark" ? "Dark" : "Light"}`;
  };

  const syncLayerSections = () => {
    logoBody.classList.toggle("bs-is-off", !logoOn.checked);
    wordBody.classList.toggle("bs-is-off", !wordOn.checked);
    queryAll<HTMLInputElement>(logoBody, "input").forEach((input) => {
      input.disabled = !logoOn.checked;
    });
    queryAll<HTMLInputElement>(wordBody, "input").forEach((input) => {
      input.disabled = !wordOn.checked;
    });
  };

  const updateMeta = () => {
    const { w, h } = dims();
    canvasDims.textContent = `${w} × ${h} px`;
    const scale = Math.max(1, Number(pngScale.value) || 1);
    pngScale.title = `PNG scale · exports at ${w * scale} × ${h * scale}`;
    exportPngBtn.title = `Export PNG · ${w * scale} × ${h * scale}`;
    exportSvgBtn.title = `Export SVG · ${w} × ${h}`;
    resetPreset.disabled = !state.dirty;
    dirtyBadge.hidden = !state.dirty;
  };

  const updatePresetHint = () => {
    const preset = presets.presets.find((item) => item.id === state.presetId);
    const { w, h } = dims();
    presetHint.textContent = `${preset ? preset.group : "Custom"} · ${w} × ${h} px${
      state.dirty ? " · edited" : ""
    }`;
  };

  const updateGalleryActive = () => {
    queryAll<HTMLButtonElement>(gallery, ".bs-pcard").forEach((card) => {
      const active = card.dataset.preset === state.presetId;
      card.classList.toggle("bs-active", active);
      card.setAttribute("aria-pressed", String(active));
    });
  };

  const markDirty = () => {
    if (state.dirty) return;
    state.dirty = true;
    updateMeta();
    updatePresetHint();
  };

  const applyCanvas = () => {
    const { w, h } = dims();
    const mode = bgmode.value;
    bg.className = `bs-bg ${
      mode === "transparent" ? "" : mode === "solid" ? "bs-solid" : `bs-field${mode === "field-anim" ? " bs-anim" : ""}`
    }`;
    bg.style.webkitMaskImage = "";
    bg.style.maskImage = "";
    bg.style.removeProperty("--field");
    if (mode !== "solid" && mode !== "transparent") {
      const url = `url(${ASSET_ROOT}/field-${fieldKey(w, h)}.svg)`;
      bg.style.setProperty("--field", url);
      bg.style.webkitMaskImage = url;
      bg.style.maskImage = url;
    }
    stage.classList.toggle("bs-checker", mode === "transparent");
  };

  const applyTheme = () => {
    const theme = palettes[themeSel.value]?.[pol.value as "dark" | "light"];
    if (!theme) return;
    for (const element of [stage, bg, logoLayer, wordLayer]) {
      element.style.setProperty("--bg", theme.bg);
      element.style.setProperty("--ink", theme.ink);
      element.style.setProperty("--accent", theme.accent);
    }
    syncThemeLabel();
  };

  const applyLayout = () => {
    logoLayer.style.display = logoOn.checked ? "flex" : "none";
    wordLayer.style.display = wordOn.checked ? "block" : "none";
    logoLayer.style.setProperty("--ls", `${logoS.value}%`);
    logoLayer.style.setProperty("--lx", `${logoX.value}%`);
    logoLayer.style.setProperty("--ly", `${logoY.value}%`);
    wordLayer.style.setProperty("--ws", `${wordS.value}%`);
    wordLayer.style.setProperty("--wx", `${wordX.value}%`);
    wordLayer.style.setProperty("--wy", `${wordY.value}%`);
    lsv.textContent = `${logoS.value}%`;
    lxv.textContent = `${logoX.value}%`;
    lyv.textContent = `${logoY.value}%`;
    wsv.textContent = `${wordS.value}%`;
    wxv.textContent = `${wordX.value}%`;
    wyv.textContent = `${wordY.value}%`;
    syncLayerSections();
  };

  const applyAnim = () => {
    for (const layer of [logoLayer, wordLayer]) {
      ANIM_CLASSES.forEach((name) => layer.classList.remove(name));
      if (animOn.checked) ANIM_CLASSES.forEach((name) => layer.classList.add(name));
    }
    replay.disabled = !animOn.checked;
  };

  const clamp = (value: number, min: number, max: number) =>
    Math.max(min, Math.min(max, value));

  const centerGroup = () => {
    const stageRect = stage.getBoundingClientRect();
    if (!stageRect.width || !stageRect.height) return;
    const layers = [logoLayer, wordLayer].filter(
      (layer) => getComputedStyle(layer).display !== "none",
    );
    if (!layers.length) return;
    const rects = layers.map((layer) => layer.getBoundingClientRect());
    const minX = Math.min(...rects.map((rect) => rect.left));
    const maxX = Math.max(...rects.map((rect) => rect.right));
    const minY = Math.min(...rects.map((rect) => rect.top));
    const maxY = Math.max(...rects.map((rect) => rect.bottom));
    const deltaX = ((stageRect.left + stageRect.width / 2 - (minX + maxX) / 2) / stageRect.width) * 100;
    const deltaY = ((stageRect.top + stageRect.height / 2 - (minY + maxY) / 2) / stageRect.height) * 100;
    const lx0 = Number(logoX.value);
    const ly0 = Number(logoY.value);
    const wx0 = Number(wordX.value);
    const wy0 = Number(wordY.value);
    const dx = clamp(deltaX, -50 - Math.min(lx0, wx0), 150 - Math.max(lx0, wx0));
    const dy = clamp(deltaY, -50 - Math.min(ly0, wy0), 150 - Math.max(ly0, wy0));
    logoX.value = (lx0 + dx).toFixed(1);
    wordX.value = (wx0 + dx).toFixed(1);
    logoY.value = (ly0 + dy).toFixed(1);
    wordY.value = (wy0 + dy).toFixed(1);
    applyLayout();
  };

  const fitStage = () => {
    const { w, h } = dims();
    if (window.innerWidth <= 980) {
      stage.style.width = "100%";
      stage.style.height = "auto";
      stage.style.aspectRatio = `${w} / ${h}`;
      return;
    }
    const aspect = w / h;
    const availableWidth = Math.max(160, canvasArea.clientWidth - 56);
    const availableHeight = Math.max(160, canvasArea.clientHeight - 56);
    let width = availableWidth;
    let height = width / aspect;
    if (height > availableHeight) {
      height = availableHeight;
      width = height * aspect;
    }
    stage.style.width = `${width}px`;
    stage.style.height = `${height}px`;
    stage.style.aspectRatio = "";
  };

  const buildPresetSelect = () => {
    presetSel.innerHTML = "";
    let group: string | null = null;
    let optgroup: HTMLOptGroupElement | null = null;
    for (const preset of presets.presets) {
      if (preset.group !== group) {
        group = preset.group;
        optgroup = document.createElement("optgroup");
        optgroup.label = group;
        presetSel.appendChild(optgroup);
      }
      const option = document.createElement("option");
      option.value = preset.id;
      option.textContent = preset.label;
      optgroup?.appendChild(option);
    }
  };

  const buildThemeOptions = () => {
    themeSel.innerHTML = "";
    const core = document.createElement("option");
    core.value = "default";
    core.textContent = "Default · mono";
    themeSel.appendChild(core);
    const group = document.createElement("optgroup");
    group.label = "Palettes";
    for (const name of Object.keys(palettes)) {
      if (name === "default") continue;
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      group.appendChild(option);
    }
    themeSel.appendChild(group);
  };

  const buildGallery = () => {
    gallery.innerHTML = "";
    const groups = new Map<string, Preset[]>();
    for (const preset of presets.presets) {
      const list = groups.get(preset.group) ?? [];
      list.push(preset);
      groups.set(preset.group, list);
    }
    for (const [groupName, items] of groups) {
      const section = document.createElement("section");
      section.className = "bs-preset-group";
      const head = document.createElement("div");
      head.className = "bs-preset-group-head";
      head.innerHTML = `<h3>${escapeXml(groupName)}</h3><span>${items.length}</span>`;
      section.appendChild(head);
      const grid = document.createElement("div");
      grid.className = "bs-preset-grid";
      for (const preset of items) {
        const settings = preset.settings;
        const theme =
          palettes[settings.theme]?.[settings.mode] ?? palettes.default?.dark;
        if (!theme) continue;
        const aspect = settings.width / settings.height;
        const aspectClass = aspect >= 1.6 ? "wide" : aspect < 1 ? "tall" : "square";
        const checker = settings.background === "transparent" ? " bs-checker" : "";
        const field =
          settings.background === "field" || settings.background === "field-anim"
            ? `<span class="bs-pfield" style="--field:url(${ASSET_ROOT}/field-${fieldKey(
                settings.width,
                settings.height,
              )}.svg)"></span>`
            : "";
        const logo = settings.logo.show ? '<span class="bs-plogo"></span>' : "";
        const word = settings.wordmark.show ? '<span class="bs-pword"></span>' : "";
        const card = document.createElement("button");
        card.type = "button";
        card.className = "bs-pcard";
        card.dataset.preset = preset.id;
        card.setAttribute("aria-pressed", "false");
        card.innerHTML =
          `<span class="bs-pthumb ${aspectClass}">` +
          `<span class="bs-pstage${checker}" style="--ar:${settings.width} / ${settings.height};--bg:${theme.bg};--ink:${theme.ink};--accent:${theme.accent}">` +
          field +
          `<span class="bs-pcontent layout-${settings.layout}" style="--ls:${settings.logo.size}%;--ws:${settings.wordmark.size}%">${logo}${word}</span>` +
          `</span></span>` +
          `<span class="bs-pmeta"><span class="bs-pname">${escapeXml(preset.label)}</span>` +
          `<span class="bs-pdims">${settings.width} × ${settings.height}</span></span>`;
        grid.appendChild(card);
      }
      section.appendChild(grid);
      gallery.appendChild(section);
    }
    galleryCount.textContent = `${gallery.querySelectorAll(".bs-pcard").length} formats`;
  };

  const applyPreset = (id: string) => {
    const preset = presets.presets.find((item) => item.id === id);
    if (!preset) return;
    const settings = preset.settings;
    state.presetId = id;
    cw.value = String(settings.width);
    ch.value = String(settings.height);
    bgmode.value = ["solid", "field", "field-anim", "transparent"].includes(settings.background)
      ? settings.background
      : "solid";
    themeSel.value = settings.theme && palettes[settings.theme] ? settings.theme : "default";
    pol.value = settings.mode === "light" ? "light" : "dark";
    layoutSel.value = LAYOUTS[settings.layout] ? settings.layout : "logo-left";
    const defaults = layoutValues(layoutSel.value);
    const logo = settings.logo ?? {};
    const word = settings.wordmark ?? {};
    logoOn.checked = logo.show != null ? Boolean(logo.show) : defaults.logo.show;
    wordOn.checked = word.show != null ? Boolean(word.show) : defaults.word.show;
    logoS.value = String(logo.size != null ? logo.size : defaults.logo.size);
    wordS.value = String(word.size != null ? word.size : defaults.word.size);
    logoX.value = String(logo.x != null ? logo.x : defaults.logo.x);
    logoY.value = String(logo.y != null ? logo.y : defaults.logo.y);
    wordX.value = String(word.x != null ? word.x : defaults.word.x);
    wordY.value = String(word.y != null ? word.y : defaults.word.y);
    animOn.checked = Boolean(settings.animated);
    applyCanvas();
    applyTheme();
    applyLayout();
    applyAnim();
    syncModeSeg();
    syncBgSeg();
    presetSel.value = id;
    state.dirty = false;
    updateMeta();
    updatePresetHint();
    updateGalleryActive();
    fitStage();
    stage.getBoundingClientRect();
    if (settings.center !== false) centerGroup();
    canvasTitle.textContent = preset.label;
    stage.setAttribute("aria-label", `${preset.label} preview`);
  };

  const applyLayoutPreset = () => {
    const defaults = layoutValues(layoutSel.value);
    logoOn.checked = defaults.logo.show;
    wordOn.checked = defaults.word.show;
    logoS.value = String(defaults.logo.size);
    logoX.value = String(defaults.logo.x);
    logoY.value = String(defaults.logo.y);
    wordS.value = String(defaults.word.size);
    wordX.value = String(defaults.word.x);
    wordY.value = String(defaults.word.y);
    applyLayout();
    stage.getBoundingClientRect();
    centerGroup();
    markDirty();
  };

  const reseed = () => {
    const random = (min: number, max: number) => Math.floor(min + Math.random() * (max - min));
    const seedPixels = (layer: HTMLElement, selector: string) => {
      queryAll<SVGRectElement>(layer, selector).forEach((element) => {
        element.style.setProperty("--d", String(random(10, 830)));
        element.style.setProperty("--fp", String(random(3200, 8400)));
        element.style.setProperty("--fd", String(random(0, 7000)));
        if (Math.random() < 0.07) element.classList.add("fx");
        else element.classList.remove("fx");
      });
    };
    const seedTiming = (layer: HTMLElement, selector: string, period: string, delay: string) => {
      queryAll<SVGRectElement>(layer, selector).forEach((element) => {
        element.style.setProperty(period, String(random(2600, 7800)));
        element.style.setProperty(delay, String(random(0, 7000)));
      });
    };
    seedPixels(logoLayer, ".px");
    seedPixels(wordLayer, ".wpx");
    seedTiming(logoLayer, ".glint", "--gp", "--gd");
    seedTiming(wordLayer, ".wglint", "--gp", "--gd");
    seedTiming(logoLayer, ".stray", "--sp", "--sd");
    seedTiming(wordLayer, ".wstray", "--sp", "--sd");
  };

  const resolvedPalette = () => {
    const styles = getComputedStyle(stage);
    const probe = document.createElement("span");
    probe.style.cssText =
      "position:absolute;left:-9999px;top:-9999px;width:0;height:0;pointer-events:none";
    document.body.appendChild(probe);
    const resolve = (value: string) => {
      probe.style.color = "";
      probe.style.color = value || "#000";
      return getComputedStyle(probe).color || "rgb(0, 0, 0)";
    };
    const palette = {
      bg: resolve(styles.getPropertyValue("--bg").trim()),
      ink: resolve(styles.getPropertyValue("--ink").trim()),
      accent: resolve(styles.getPropertyValue("--accent").trim()),
    };
    probe.remove();
    return palette;
  };

  const staticLogo = (source: string, bgColor: string, ink: string, accent: string) => {
    const key = `${bgColor}|${ink}|${accent}`;
    if (logoCache.key === key) return logoCache.value;
    const value = source.replace(/<rect\b([^>]*?)(?:\/>|>\s*<\/rect>)/g, (_match, attrs: string) => {
      const className = (attrs.match(/class="([^"]*)"/) ?? [])[1] ?? "";
      if (/\b(glint|stray)\b/.test(className)) return "";
      let tone: string;
      if (/\baccent\b/.test(className)) tone = accent;
      else if (/\bmid\b/.test(className)) tone = mix(ink, bgColor, 0.52);
      else if (/\bdim\b/.test(className)) tone = mix(ink, bgColor, 0.26);
      else tone = ink;
      let fill: string;
      if (/\bf-left\b/.test(className)) fill = mix(tone, bgColor, 0.78);
      else if (/\bf-right\b/.test(className)) fill = mix(tone, bgColor, 0.56);
      else fill = tone;
      const clean = attrs.replace(/\sclass="[^"]*"/, "").replace(/\sstyle="[^"]*"/g, "");
      return `<rect fill="${fill}"${clean}/>`;
    });
    logoCache = { key, value };
    return value;
  };

  const staticWordmark = (source: string, ink: string) => {
    if (wordCache.key === ink) return wordCache.value;
    const value = source.replace(/<rect\b([^>]*?)(?:\/>|>\s*<\/rect>)/g, (_match, attrs: string) => {
      const className = (attrs.match(/class="([^"]*)"/) ?? [])[1] ?? "";
      if (/\b(wglint|wstray)\b/.test(className)) return "";
      let clean = attrs.replace(/\sclass="[^"]*"/, "").replace(/\sstyle="[^"]*"/g, "");
      clean = clean.replace(/fill="currentColor"/g, `fill="${ink}"`);
      return `<rect${clean}/>`;
    });
    wordCache = { key: ink, value };
    return value;
  };

  const fieldData = async (name: string, ink: string): Promise<FieldData> => {
    const key = `${name}|${ink}`;
    const cached = fieldCache.get(key);
    if (cached) return cached;
    const source = await getText(`${ASSET_ROOT}/field-${name}.svg`, signal);
    const match = source.match(/viewBox="([^"]+)"/);
    const viewBox = match ? match[1].trim().split(/\s+/).map(Number) : [0, 0, 1, 1];
    const inner = source
      .replace(/^[\s\S]*?<svg[^>]*>/, "")
      .replace(/<\/svg>\s*$/, "")
      .replace(/fill="currentColor"/g, `fill="${ink}"`);
    const data = { inner, fw: viewBox[2] || 1, fh: viewBox[3] || 1 };
    fieldCache.set(key, data);
    return data;
  };

  const composeSvg = async (scale = 1) => {
    const { w, h } = dims();
    const { bg: bgColor, ink, accent } = resolvedPalette();
    const mode = bgmode.value;
    const parts: string[] = [];
    if (mode !== "transparent") {
      parts.push(`<rect width="${w}" height="${h}" fill="${bgColor}"/>`);
    }
    if (mode === "field" || mode === "field-anim") {
      const field = await fieldData(fieldKey(w, h), ink);
      if (field.inner) {
        parts.push(
          `<svg x="0" y="0" width="${w}" height="${h}" viewBox="0 0 ${field.fw} ${field.fh}" preserveAspectRatio="none" shape-rendering="crispEdges">${field.inner}</svg>`,
        );
      }
    }
    const logoEl = logoLayer.querySelector("svg");
    const wordEl = wordLayer.querySelector("svg");
    const logoSource = logoEl?.innerHTML ?? "";
    const wordSource = wordEl?.innerHTML ?? "";
    const readBox = (element: SVGSVGElement | null, fallbackWidth: number, fallbackHeight: number) => {
      const values = element?.getAttribute("viewBox")?.trim().split(/\s+/).map(Number);
      return { w: values?.[2] || fallbackWidth, h: values?.[3] || fallbackHeight };
    };
    const logoBox = readBox(logoEl, 100, 100);
    const wordBox = readBox(wordEl, 88, 10);
    if (logoOn.checked && logoSource) {
      const x = (Number(logoX.value) / 100) * w;
      const y = (Number(logoY.value) / 100) * h;
      const size = (Number(logoS.value) / 100) * h;
      parts.push(
        `<g transform="translate(${round(x)} ${round(y)}) scale(${round(size / logoBox.h)}) translate(${round(-logoBox.w / 2)} ${round(-logoBox.h / 2)})" shape-rendering="crispEdges">${staticLogo(logoSource, bgColor, ink, accent)}</g>`,
      );
    }
    if (wordOn.checked && wordSource) {
      const x = (Number(wordX.value) / 100) * w;
      const y = (Number(wordY.value) / 100) * h;
      const size = (Number(wordS.value) / 100) * h;
      parts.push(
        `<g transform="translate(${round(x)} ${round(y)}) scale(${round(size / wordBox.h)}) translate(${round(-wordBox.w / 2)} ${round(-wordBox.h / 2)})" shape-rendering="crispEdges">${staticWordmark(wordSource, ink)}</g>`,
      );
    }
    const preset = presets.presets.find((item) => item.id === state.presetId);
    const title = escapeXml(
      `${preset ? preset.label : state.presetId}${state.dirty ? " (custom)" : ""} · ${w} × ${h}`,
    );
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${w * scale}" height="${h * scale}" viewBox="0 0 ${w} ${h}" shape-rendering="crispEdges"><title>${title}</title>${parts.join("")}</svg>`;
  };

  const svgToPngBlob = (svg: string, w: number, h: number): Promise<Blob> =>
    new Promise((resolve, reject) => {
      const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const image = new Image();
      image.onload = () => {
        try {
          const canvas = document.createElement("canvas");
          canvas.width = w;
          canvas.height = h;
          const context = canvas.getContext("2d");
          if (!context) throw new Error("2D canvas unavailable");
          context.clearRect(0, 0, w, h);
          context.drawImage(image, 0, 0, w, h);
          canvas.toBlob((result) => {
            URL.revokeObjectURL(url);
            if (result) resolve(result);
            else reject(new Error("PNG encode failed"));
          }, "image/png");
        } catch (error) {
          URL.revokeObjectURL(url);
          reject(error);
        }
      };
      image.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("SVG rasterization failed"));
      };
      image.src = url;
    });

  const download = (blob: Blob, name: string) => {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  };

  const baseName = () => {
    const { w, h } = dims();
    return `digithings-${state.presetId}${state.dirty ? "-custom" : ""}-${w}x${h}`;
  };

  const toast = (message: string) => {
    toastEl.textContent = message;
    toastEl.classList.add("bs-show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("bs-show"), 2600);
  };

  const setExporting = (on: boolean) => {
    state.exporting = on;
    exportPngBtn.disabled = on;
    exportSvgBtn.disabled = on;
    exportPngBtn.classList.toggle("bs-is-busy", on);
    exportSvgBtn.classList.toggle("bs-is-busy", on);
    exportPngBtn.setAttribute("aria-busy", String(on));
  };

  const exportPng = async () => {
    if (state.exporting) return;
    const scale = Math.max(1, Number(pngScale.value) || 1);
    const { w, h } = dims();
    if (w * scale * h * scale > 16_000_000) {
      toast("PNG too large — use 1× or a smaller canvas");
      return;
    }
    setExporting(true);
    try {
      const blob = await svgToPngBlob(await composeSvg(scale), w * scale, h * scale);
      download(blob, `${baseName()}${scale > 1 ? `@${scale}x` : ""}.png`);
      toast(`PNG exported · ${w * scale} × ${h * scale}`);
    } catch (error) {
      if (!signal.aborted) {
        console.error("brand studio: PNG export failed", error);
        toast("PNG export failed — see console");
      }
    } finally {
      if (!disposed) setExporting(false);
    }
  };

  const exportSvg = async () => {
    if (state.exporting) return;
    setExporting(true);
    try {
      const { w, h } = dims();
      const blob = new Blob([await composeSvg(1)], { type: "image/svg+xml;charset=utf-8" });
      download(blob, `${baseName()}.svg`);
      toast(`SVG exported · ${w} × ${h}`);
    } catch (error) {
      if (!signal.aborted) {
        console.error("brand studio: SVG export failed", error);
        toast("SVG export failed — see console");
      }
    } finally {
      if (!disposed) setExporting(false);
    }
  };

  const onDimInput = () => {
    applyCanvas();
    fitStage();
    updateMeta();
    updatePresetHint();
    markDirty();
  };

  const replayAnim = () => {
    if (!animOn.checked) return;
    reseed();
    for (const layer of [logoLayer, wordLayer]) {
      ANIM_CLASSES.forEach((name) => layer.classList.remove(name));
    }
    void stage.getBoundingClientRect();
    applyAnim();
  };

  const onReady = async () => {
    const [presetData, paletteData, logoSource, wordSource] = await Promise.all([
      getJson<PresetsFile>(`${ASSET_ROOT}/presets.json`, signal),
      getJson<Palettes>(`${ASSET_ROOT}/palettes.json`, signal),
      getText(`${ASSET_ROOT}/logo-animated.svg`, signal),
      getText(`${ASSET_ROOT}/wordmark-animated.svg`, signal),
    ]);
    if (disposed) return;
    presets = presetData;
    palettes = paletteData;
    if (palettes.default) {
      palettes.default.dark.accent = palettes.default.dark.ink;
      palettes.default.light.accent = palettes.default.light.ink;
    }
    logoLayer.innerHTML = logoSource;
    wordLayer.innerHTML = wordSource;
    buildPresetSelect();
    buildThemeOptions();
    buildGallery();
    reseed();

    presetSel.addEventListener("change", () => applyPreset(presetSel.value), { signal });
    resetPreset.addEventListener("click", () => applyPreset(state.presetId), { signal });
    cw.addEventListener("input", onDimInput, { signal });
    ch.addEventListener("input", onDimInput, { signal });
    cw.addEventListener("change", () => { cw.value = String(dims().w); }, { signal });
    ch.addEventListener("change", () => { ch.value = String(dims().h); }, { signal });
    queryAll<HTMLButtonElement>(root, "#bs-bgSeg button").forEach((button) => {
      button.addEventListener("click", () => {
        bgmode.value = button.dataset.bg ?? "solid";
        applyCanvas();
        syncBgSeg();
        markDirty();
        updateMeta();
      }, { signal });
    });
    themeSel.addEventListener("change", () => { applyTheme(); markDirty(); }, { signal });
    queryAll<HTMLButtonElement>(root, "#bs-modeSeg button").forEach((button) => {
      button.addEventListener("click", () => {
        pol.value = button.dataset.mode === "light" ? "light" : "dark";
        applyTheme();
        syncModeSeg();
        markDirty();
      }, { signal });
    });
    layoutSel.addEventListener("change", applyLayoutPreset, { signal });
    [logoS, logoX, logoY, wordS, wordX, wordY].forEach((input) => {
      input.addEventListener("input", () => { applyLayout(); markDirty(); }, { signal });
    });
    logoOn.addEventListener("change", () => {
      if (logoOn.checked && Number(logoS.value) === 10) logoS.value = "36";
      applyLayout();
      stage.getBoundingClientRect();
      centerGroup();
      markDirty();
    }, { signal });
    wordOn.addEventListener("change", () => {
      if (wordOn.checked && Number(wordS.value) === 10) wordS.value = "20";
      applyLayout();
      stage.getBoundingClientRect();
      centerGroup();
      markDirty();
    }, { signal });
    animOn.addEventListener("change", applyAnim, { signal });
    replay.addEventListener("click", replayAnim, { signal });
    centerBtn.addEventListener("click", () => {
      centerGroup();
      markDirty();
    }, { signal });
    pngScale.addEventListener("change", updateMeta, { signal });
    exportPngBtn.addEventListener("click", () => { void exportPng(); }, { signal });
    exportSvgBtn.addEventListener("click", () => { void exportSvg(); }, { signal });
    gallery.addEventListener("click", (event) => {
      const target = event.target as HTMLElement | null;
      const card = target?.closest<HTMLButtonElement>(".bs-pcard");
      if (!card) return;
      applyPreset(card.dataset.preset ?? "");
      if (window.innerWidth <= 980) {
        root.querySelector(".bs-canvas-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, { signal });

    if (presets.presets.length) applyPreset(presets.presets[0].id);
    root.setAttribute("aria-busy", "false");
    exportPngBtn.disabled = false;
    exportSvgBtn.disabled = false;
    requestAnimationFrame(fitStage);

    const resizeObserver = new ResizeObserver(() => {
      cancelAnimationFrame(fitFrame);
      fitFrame = requestAnimationFrame(fitStage);
    });
    resizeObserver.observe(canvasArea);
    signal.addEventListener("abort", () => resizeObserver.disconnect(), { once: true });
    window.addEventListener("resize", () => {
      cancelAnimationFrame(fitFrame);
      fitFrame = requestAnimationFrame(fitStage);
    }, { signal });
  };

  void onReady().catch((error: unknown) => {
    if (signal.aborted || disposed) return;
    console.error("brand studio: could not load the studio assets", error);
    root.setAttribute("aria-busy", "false");
    presetHint.textContent = "Could not load the studio assets. Check the console.";
  });

  return () => {
    disposed = true;
    controller.abort();
    cancelAnimationFrame(fitFrame);
    clearTimeout(toastTimer);
  };
}
