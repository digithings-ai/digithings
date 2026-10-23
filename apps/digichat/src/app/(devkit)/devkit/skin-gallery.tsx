"use client";

/**
 * Visual skin gallery for the devkit Appearance section (#6327 UD1).
 *
 * Replaces the skin `Select` with a grid of every registered `THREAD_SKINS`
 * entry, so picking a skin is recognition rather than a dropdown scroll. The
 * registry stays the single source of truth: ids and modes are derived from
 * `thread-skins.ts`, never re-typed here.
 *
 * Colour comes from the generated token tables — `PALETTES` for a deployment
 * that pins a palette, `designTokens` (the canon default) otherwise. No hex
 * literal lives in this file: a skin card paints tokens, so it can never drift
 * from the canon palette. Each card shows its light AND dark pair, and the
 * selected skin repeats both pairs with the WCAG ratio for its accent/on-accent
 * pair (the same `contrast()` helper the accent readout uses).
 *
 * Selection commits the draft through the caller (`chrome.skin` text rewrite).
 * It never saves — the devkit save button is the only writer.
 */

import { useId, useRef } from "react";
import {
  CLONE_SKINS,
  LAYOUT_SKINS,
  THREAD_SKINS,
  type ThreadSkin,
} from "@digithings/ui/chat/skins";
import { designTokens } from "@digithings/design/tokens";
import { PALETTES, isPaletteId } from "@digithings/ui/theme";
import { CONTRAST_MINIMUM, contrast } from "./devkit-contrast";

/** Where a skin sits in the registry (what it does, not what it looks like). */
export type SkinMode = "first-party" | "layout" | "clone" | "catalog";

/** The two theme pairs every card previews, in render order. */
export const SKIN_GALLERY_THEMES = ["light", "dark"] as const;

export type SkinGalleryTheme = (typeof SKIN_GALLERY_THEMES)[number];

/** One theme's resolved token pair (all `#rrggbb`, straight from the tables). */
export type SkinTokenPair = {
  bg: string;
  surface: string;
  ink: string;
  accent: string;
  onAccent: string;
};

export function skinMode(skin: ThreadSkin): SkinMode {
  if (skin === "digichat") return "first-party";
  if ((LAYOUT_SKINS as readonly string[]).includes(skin)) return "layout";
  if ((CLONE_SKINS as readonly string[]).includes(skin)) return "clone";
  return "catalog";
}

/**
 * Resolve the light/dark token pair for a deployment palette. An unknown or
 * absent palette falls back to the canon default table, which is exactly what
 * `:root` / `:root[data-theme]` paint.
 */
export function skinTokenPair(
  palette: string | undefined,
  theme: SkinGalleryTheme,
): SkinTokenPair {
  if (palette !== undefined && isPaletteId(palette)) {
    const pair = PALETTES[palette][theme];
    return {
      bg: pair.bg,
      surface: pair.surface,
      ink: pair.ink,
      accent: pair.accent,
      onAccent: pair.onAccent,
    };
  }
  const pair = designTokens[theme];
  return {
    bg: pair.bg.hex,
    surface: pair.surface.hex,
    ink: pair.ink.hex,
    accent: pair.accent.hex,
    onAccent: pair["on-accent"].hex,
  };
}

/** WCAG ratio for the pair's accent/on-accent text (the copied-accent test). */
export function pairContrast(pair: SkinTokenPair): number {
  return contrast(pair.accent, pair.onAccent);
}

function SwatchStrip({ pair }: { pair: SkinTokenPair }) {
  const chips = [pair.bg, pair.surface, pair.ink, pair.accent];
  return (
    <span className="flex gap-[0.15rem]" aria-hidden="true">
      {chips.map((hex, i) => (
        <span
          key={`${hex}-${i}`}
          className="h-2.5 w-3 border border-hair"
          style={{ backgroundColor: hex }}
        />
      ))}
    </span>
  );
}

export function SkinGallery({
  value,
  palette,
  onCommit,
}: {
  /** The draft's `chrome.skin`; unknown values show no selection. */
  value: string | undefined;
  /** The draft's `chrome.palette` (optional — default tokens otherwise). */
  palette?: string;
  /** Returns whether the draft commit applied (the highlight reverts on false). */
  onCommit: (skin: ThreadSkin) => boolean;
}) {
  const labelId = useId();
  const cards = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIndex = THREAD_SKINS.findIndex((skin) => skin === value);
  const selected = selectedIndex >= 0 ? THREAD_SKINS[selectedIndex] : null;

  const pick = (skin: ThreadSkin) => {
    onCommit(skin);
  };

  const move = (from: number, to: number) => {
    const next = (to + THREAD_SKINS.length) % THREAD_SKINS.length;
    cards.current[next]?.focus();
    pick(THREAD_SKINS[next]);
  };

  return (
    <div className="grid min-w-0 gap-1.5">
      <span
        id={labelId}
        className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute"
      >
        skin — pick one
      </span>
      <div
        role="group"
        aria-labelledby={labelId}
        className="grid min-w-0 grid-cols-2 gap-1 sm:grid-cols-3"
      >
        {THREAD_SKINS.map((skin, i) => {
          const mode = skinMode(skin);
          const active = skin === selected;
          return (
            <button
              key={skin}
              ref={(el) => {
                cards.current[i] = el;
              }}
              type="button"
              data-skin={skin}
              aria-pressed={active}
              aria-label={`skin ${skin} (${mode})`}
              tabIndex={active || (selected === null && i === 0) ? 0 : -1}
              className={`grid min-w-0 gap-1 border px-[0.4rem] py-[0.35rem] text-left transition-colors ${
                active
                  ? "border-accent bg-accent-weak text-ink"
                  : "border-hair bg-surface text-ink-soft hover:text-ink"
              }`}
              onClick={() => pick(skin)}
              onKeyDown={(event) => {
                if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                  event.preventDefault();
                  move(i, i + 1);
                } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
                  event.preventDefault();
                  move(i, i - 1);
                } else if (event.key === "Home") {
                  event.preventDefault();
                  move(i, 0);
                } else if (event.key === "End") {
                  event.preventDefault();
                  move(i, THREAD_SKINS.length - 1);
                }
              }}
            >
              <span className="flex min-w-0 items-baseline justify-between gap-1">
                <span className="truncate font-mono text-[0.7rem]">{skin}</span>
                <span className="shrink-0 font-mono text-[0.55rem] uppercase tracking-[0.1em] text-ink-mute">
                  {mode}
                </span>
              </span>
              {SKIN_GALLERY_THEMES.map((theme) => (
                <span key={theme} className="flex items-center gap-1">
                  <span className="w-7 shrink-0 font-mono text-[0.5rem] uppercase tracking-[0.1em] text-ink-mute">
                    {theme}
                  </span>
                  <SwatchStrip pair={skinTokenPair(palette, theme)} />
                </span>
              ))}
            </button>
          );
        })}
      </div>
      {selected ? (
        <div
          className="grid min-w-0 gap-0.5 border-t border-hair pt-1"
          data-testid="skin-gallery-pairs"
        >
          {SKIN_GALLERY_THEMES.map((theme) => {
            const pair = skinTokenPair(palette, theme);
            const ratio = pairContrast(pair);
            const below = ratio < CONTRAST_MINIMUM;
            return (
              <p
                key={theme}
                className="font-mono text-[0.6rem] text-ink-mute"
                data-testid={`skin-pair-${theme}`}
              >
                <span className="uppercase tracking-[0.1em]">{theme}</span>{" "}
                {selected} · contrast {ratio.toFixed(2)}:1
                {below ? " — below the 4.5:1 (WCAG AA) minimum" : ""}
              </p>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
