/**
 * Preference ledger for the utilitarian-terminal iterate gallery.
 * Each axis stores one selected variant id in localStorage (`dr-util-prefs`).
 * The /iterate page reads/writes via useSyncExternalStore; BLEND.md is the
 * human-readable mirror once a round of picks is locked.
 */

export type UtilAxis = {
  id: string;
  label: string;
  prompt: string;
  variants: UtilVariant[];
};

export type UtilVariant = {
  id: string;
  label: string;
  inspiredBy: string;
  note: string;
};

const KEY = "dr-util-prefs";
const EVENT = "dr-util-prefs-change";

export const UTIL_AXES: UtilAxis[] = [
  {
    id: "radius-controls",
    label: "Control radius",
    prompt: "How sharp should buttons, chips, and nav controls be?",
    variants: [
      {
        id: "pill",
        label: "Pill",
        inspiredBy: "digiweb current",
        note: "999px — shape means actionable",
      },
      {
        id: "soft",
        label: "Soft rect",
        inspiredBy: "agentmail",
        note: "6–8px — quiet product SaaS",
      },
      {
        id: "sharp",
        label: "Sharp",
        inspiredBy: "Factory / Warp",
        note: "2–4px — instrument chrome",
      },
      {
        id: "zero",
        label: "Zero",
        inspiredBy: "herdr",
        note: "0px — brutalist marketing chrome",
      },
    ],
  },
  {
    id: "radius-cards",
    label: "Card / panel radius",
    prompt: "Containers and product frames.",
    variants: [
      {
        id: "soft",
        label: "Soft 12",
        inspiredBy: "digiweb current",
        note: "8 / 12 / 16 scale",
      },
      {
        id: "tight",
        label: "Tight 4",
        inspiredBy: "Linear",
        note: "4–6px panels",
      },
      {
        id: "zero",
        label: "Zero slab",
        inspiredBy: "herdr",
        note: "Hairline rectangle only",
      },
    ],
  },
  {
    id: "type-voice",
    label: "Type voice",
    prompt: "What carries headlines and chrome?",
    variants: [
      {
        id: "serif-claim",
        label: "Serif claim",
        inspiredBy: "digiweb current",
        note: "Instrument / Fraunces display + Geist body + mono chrome",
      },
      {
        id: "util-sans",
        label: "Utilitarian sans",
        inspiredBy: "agentmail / Vercel",
        note: "Geist Sans for display + body; mono only for data",
      },
      {
        id: "mono-all",
        label: "Mono everything",
        inspiredBy: "omarchy / xAI",
        note: "JetBrains Mono or Geist Mono at every size",
      },
      {
        id: "sans-mono",
        label: "Sans + mono chrome",
        inspiredBy: "herdr / Factory",
        note: "Sans headlines; uppercase mono labels",
      },
    ],
  },
  {
    id: "primary-cta",
    label: "Primary CTA",
    prompt: "The one loud control per viewport.",
    variants: [
      {
        id: "accent-pill",
        label: "Accent pill",
        inspiredBy: "digiweb current",
        note: "Solid --accent, pill shape",
      },
      {
        id: "white-rect",
        label: "White rect",
        inspiredBy: "agentmail / xAI",
        note: "Paper fill on dark, sharp corners",
      },
      {
        id: "ink-sharp",
        label: "Ink sharp",
        inspiredBy: "Factory",
        note: "Near-black fill, light label, 2–3px radius",
      },
      {
        id: "outline-only",
        label: "Outline loud",
        inspiredBy: "Hyperstudio",
        note: "Hairline + weight; fill reserved for rare moments",
      },
    ],
  },
  {
    id: "nav-chrome",
    label: "Nav chrome",
    prompt: "Top-bar link language.",
    variants: [
      {
        id: "mixed",
        label: "Mixed case",
        inspiredBy: "digiweb current",
        note: "Sentence case sans / mono mix",
      },
      {
        id: "upper-mono",
        label: "Upper mono",
        inspiredBy: "herdr",
        note: "11–12px uppercase, tracked, mono",
      },
      {
        id: "sparse-ghost",
        label: "Sparse ghost",
        inspiredBy: "agentmail",
        note: "Few links, quiet; one filled Login",
      },
    ],
  },
  {
    id: "kicker",
    label: "Section kicker",
    prompt: "The tiny label above a section title.",
    variants: [
      {
        id: "slash-comment",
        label: "// comment",
        inspiredBy: "digiweb / xAI",
        note: "Mono `// section` kicker",
      },
      {
        id: "upper-track",
        label: "Upper tracked",
        inspiredBy: "herdr",
        note: "Uppercase + wide tracking + hairline rule",
      },
      {
        id: "plain-mute",
        label: "Plain mute",
        inspiredBy: "agentmail",
        note: "Small mute sans, no ornament",
      },
    ],
  },
  {
    id: "hero",
    label: "Hero composition",
    prompt: "First viewport job.",
    variants: [
      {
        id: "claim-mesh",
        label: "Claim + atmosphere",
        inspiredBy: "digiweb current",
        note: "Headline + mesh/graph atmosphere",
      },
      {
        id: "claim-curl",
        label: "Claim + install",
        inspiredBy: "herdr",
        note: "Headline + curl install box + trust meta",
      },
      {
        id: "split-live",
        label: "Split live proof",
        inspiredBy: "agentmail",
        note: "Copy left / live code or terminal right",
      },
      {
        id: "mono-center",
        label: "Mono center",
        inspiredBy: "omarchy",
        note: "Centered mono claim + icon CTA strip",
      },
    ],
  },
  {
    id: "density",
    label: "Density / spacing",
    prompt: "How much air between sections?",
    variants: [
      {
        id: "generous",
        label: "Generous",
        inspiredBy: "digiweb current",
        note: "clamp(4rem, 8vw, 7rem) sections",
      },
      {
        id: "instrument",
        label: "Instrument",
        inspiredBy: "Linear / Factory",
        note: "~64–96px; tighter element gaps",
      },
      {
        id: "sparse",
        label: "Sparse",
        inspiredBy: "agentmail",
        note: "More air, fewer competing blocks",
      },
    ],
  },
  {
    id: "surfaces",
    label: "Surfaces",
    prompt: "How do panels sit on the canvas?",
    variants: [
      {
        id: "soft-card",
        label: "Soft card",
        inspiredBy: "digiweb current",
        note: "--surface fill + hairline + soft radius",
      },
      {
        id: "hairline-panel",
        label: "Hairline panel",
        inspiredBy: "Hyperstudio / Linear",
        note: "Flat; border does the work",
      },
      {
        id: "contrast-slab",
        label: "Contrast slab",
        inspiredBy: "Factory",
        note: "Light panel on dark canvas (or inverse)",
      },
    ],
  },
  {
    id: "stats",
    label: "Stat strip",
    prompt: "Social proof / metrics row.",
    variants: [
      {
        id: "quiet-row",
        label: "Quiet row",
        inspiredBy: "digiweb current",
        note: "Modest mono figures",
      },
      {
        id: "huge-mono",
        label: "Huge mono",
        inspiredBy: "herdr",
        note: "Oversized tabular numbers + tiny labels",
      },
      {
        id: "none",
        label: "No strip",
        inspiredBy: "omarchy",
        note: "Skip metrics; product shot speaks",
      },
    ],
  },
  {
    id: "inputs",
    label: "Form inputs",
    prompt: "Fields and search.",
    variants: [
      {
        id: "soft-field",
        label: "Soft field",
        inspiredBy: "digiweb current",
        note: "8px, canvas fill, hairline",
      },
      {
        id: "sharp-field",
        label: "Sharp field",
        inspiredBy: "herdr terminal",
        note: "0–2px, mono value",
      },
      {
        id: "underline",
        label: "Underline only",
        inspiredBy: "brutalist docs",
        note: "No box — bottom rule only",
      },
    ],
  },
  {
    id: "docs-control",
    label: "Secondary docs control",
    prompt: "The quiet sibling of the primary CTA.",
    variants: [
      {
        id: "ghost-pill",
        label: "Ghost pill",
        inspiredBy: "digiweb current",
        note: "Hairline pill",
      },
      {
        id: "ghost-sharp",
        label: "Ghost sharp",
        inspiredBy: "Factory",
        note: "Hairline rectangle",
      },
      {
        id: "bracket",
        label: "Bracket corners",
        inspiredBy: "agentmail",
        note: "Corner ticks instead of full border",
      },
    ],
  },
];

type PrefMap = Record<string, string>;

let cachedSnapshot: PrefMap | null = null;

function readRaw(): PrefMap {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as PrefMap;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

export function getUtilPrefsSnapshot(): PrefMap {
  if (!cachedSnapshot) {
    cachedSnapshot = readRaw();
  }
  return cachedSnapshot;
}

const SERVER_SNAPSHOT: PrefMap = {};

export function getUtilPrefsServerSnapshot(): PrefMap {
  return SERVER_SNAPSHOT;
}

export function subscribeUtilPrefs(callback: () => void) {
  const onChange = () => {
    cachedSnapshot = null;
    callback();
  };
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function setUtilPref(axisId: string, variantId: string) {
  const next = { ...readRaw(), [axisId]: variantId };
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* private mode */
  }
  cachedSnapshot = next;
  window.dispatchEvent(new CustomEvent(EVENT));
}

export function clearUtilPrefs() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* private mode */
  }
  cachedSnapshot = {};
  window.dispatchEvent(new CustomEvent(EVENT));
}

export function formatUtilPrefsMarkdown(prefs: PrefMap): string {
  const lines = [
    "## Preference ledger (exported)",
    "",
    `| Axis | Pick | Inspired by |`,
    `| ---- | ---- | ----------- |`,
  ];
  for (const axis of UTIL_AXES) {
    const pick = prefs[axis.id];
    const variant = axis.variants.find((v) => v.id === pick);
    lines.push(
      `| ${axis.label} | ${variant ? variant.label : "_open_"} | ${variant ? variant.inspiredBy : "—"} |`,
    );
  }
  return lines.join("\n");
}
