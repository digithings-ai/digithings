/**
 * Tenant brand skin: fonts, two extra brand colours and the control shape,
 * layered on top of `accent` for one tenant's chat (`chrome.brand` in the
 * deploy YAML, `brand` on an embed tenant row).
 *
 * Kept pure (no React / window). The fonts are self-hosted with next/font in
 * the (digichat) root layout, so the CSP's `font-src 'self'` holds: a tenant
 * names a font from BRAND_FONTS, never a URL. Adding a font means one
 * next/font call in that layout plus one entry here.
 */
import type { CSSProperties } from "react";
import { z } from "zod";

import { HEX_COLOR } from "@/lib/hex-color";

/** Font id → the CSS variable next/font sets on <html> for it. */
export const BRAND_FONTS = {
  cabin: "--font-brand-cabin",
  mulish: "--font-brand-mulish",
} as const;

export type BrandFontId = keyof typeof BRAND_FONTS;
export const BRAND_FONT_IDS = Object.keys(BRAND_FONTS) as BrandFontId[];

const BrandFontSchema = z.enum(BRAND_FONT_IDS as [BrandFontId, ...BrandFontId[]]);
const Hex = z.string().regex(HEX_COLOR, "must be #rrggbb");

export const BrandSkinSchema = z
  .object({
    fonts: z
      .object({ heading: BrandFontSchema.optional(), body: BrandFontSchema.optional() })
      .strict()
      .optional(),
    colors: z
      .object({
        /** Second brand colour: links and focus rings. */
        secondary: Hex.optional(),
        /** Body text in light mode. */
        ink: Hex.optional(),
        /** Chip / user-bubble fill in light mode (dark mode derives it from the accent). */
        tint: Hex.optional(),
      })
      .strict()
      .optional(),
    /** `pill` rounds the composer, send button and suggestion chips fully. */
    shape: z.enum(["default", "pill"]).optional(),
  })
  .strict();

export type BrandSkin = z.infer<typeof BrandSkinSchema>;

/** Validate a registry value; throws with `ctx` so a bad row fails loudly like `accent`. */
export function parseBrandSkin(raw: unknown, ctx: string): BrandSkin | undefined {
  if (raw === undefined) return undefined;
  const parsed = BrandSkinSchema.safeParse(raw);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    throw new Error(`${ctx}: brand.${issue?.path.join(".") ?? ""} ${issue?.message ?? "is invalid"}`);
  }
  return parsed.data;
}

function fontStack(id: BrandFontId | undefined): string | undefined {
  return id ? `var(${BRAND_FONTS[id]}), ui-sans-serif, system-ui, sans-serif` : undefined;
}

/** Inline custom properties for the chat wrapper; undefined when there is no brand. */
export function brandSkinStyle(brand: BrandSkin | null | undefined): CSSProperties | undefined {
  if (!brand) return undefined;
  const style: Record<string, string> = {};
  const heading = fontStack(brand.fonts?.heading);
  const body = fontStack(brand.fonts?.body);
  if (heading) style["--brand-heading-font"] = heading;
  if (body) style["--brand-body-font"] = body;
  if (brand.colors?.secondary) style["--brand-secondary"] = brand.colors.secondary;
  if (brand.colors?.ink) style["--brand-ink"] = brand.colors.ink;
  if (brand.colors?.tint) style["--brand-tint"] = brand.colors.tint;
  return Object.keys(style).length ? (style as CSSProperties) : undefined;
}

/** Data attributes the BRAND_SKIN_CSS selectors key off. */
export function brandSkinAttrs(
  brand: BrandSkin | null | undefined,
): Record<string, string> | undefined {
  if (!brand) return undefined;
  const attrs: Record<string, string> = { "data-brand": "1" };
  if (brand.fonts?.body) attrs["data-brand-body"] = "1";
  if (brand.fonts?.heading) attrs["data-brand-heading"] = "1";
  if (brand.colors?.ink) attrs["data-brand-ink"] = "1";
  if (brand.colors?.tint) attrs["data-brand-tint"] = "1";
  if (brand.colors?.secondary) attrs["data-brand-secondary"] = "1";
  if (brand.shape === "pill") attrs["data-brand-shape"] = "pill";
  return attrs;
}

/**
 * Scoped to `[data-brand]`, so a tenant without a brand renders byte-for-byte
 * as before. Injected after the skin's stylesheets, so equal specificity wins.
 * `--tenant-accent` is the tenant's own accent: the digichat thread redefines
 * `--accent` to its ink token (see embed-accent-style.ts).
 */
export const BRAND_SKIN_CSS = `
[data-brand-body] .digichat-thread,
[data-brand-body] .digichat-thread :where(p, li, span, a, button, textarea, input, div, strong, em) {
  font-family: var(--brand-body-font);
  letter-spacing: normal;
}
[data-brand-body] .digichat-thread :is(strong, b, .aui-md-strong) { font-weight: 700; }
[data-brand-body] .digichat-thread :is(pre, code, kbd, samp, pre *, code *) {
  font-family: var(--font-geist-mono, ui-monospace, monospace);
}
[data-brand-heading] .digichat-thread :is(h1, h2, h3, h4, .aui-thread-welcome-message-inner) {
  font-family: var(--brand-heading-font);
  font-weight: 700;
  letter-spacing: -0.01em;
}
[data-brand-heading] .digichat-thread .aui-thread-welcome-message-inner { font-size: 2.25rem; line-height: 1.15; }
.light[data-brand-ink] .digichat-thread { --ink: var(--brand-ink); color: var(--brand-ink); }
.light[data-brand-ink] .digichat-thread :is(.aui-md-p, .aui-md-li, .aui-thread-welcome-copy) { color: var(--brand-ink); }
[data-brand] .digichat-thread .aui-thread-welcome-suggestions {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 0.5rem;
}
[data-brand] .digichat-thread .aui-thread-welcome-suggestion {
  color: var(--tenant-accent);
  background: color-mix(in srgb, var(--tenant-accent) 14%, transparent);
  border: 1px solid transparent;
  display: inline-flex;
  width: auto;
  max-width: 100%;
  padding: 0.5rem 1.1rem;
  font-weight: 600;
  transition: background-color 120ms ease, border-color 120ms ease;
}
.light[data-brand-tint] .digichat-thread .aui-thread-welcome-suggestion { background: var(--brand-tint); }
[data-brand] .digichat-thread .aui-thread-welcome-suggestion:hover { border-color: var(--tenant-accent); }
[data-brand] .digichat-thread .aui-thread-welcome-suggestion :is(.aui-msg-marker, .aui-thread-welcome-suggestion-mark) { display: none; }
[data-brand] .digichat-thread .aui-thread-welcome-suggestion-text { color: inherit; }
[data-brand] .digichat-thread .aui-composer-send {
  background: var(--tenant-accent);
  color: var(--accent-foreground, #fff);
}
[data-brand] .digichat-thread .aui-user-message-content-wrapper {
  background: color-mix(in srgb, var(--tenant-accent) 14%, transparent);
  padding: 0.6rem 1rem;
}
.light[data-brand-tint] .digichat-thread .aui-user-message-content-wrapper { background: var(--brand-tint); }
[data-brand-secondary] .digichat-thread .aui-md-a { color: var(--brand-secondary); font-weight: 600; }
.dark[data-brand-secondary] .digichat-thread .aui-md-a { color: color-mix(in srgb, var(--brand-secondary) 55%, #fff); }
[data-brand-secondary] .digichat-thread .aui-md-a:hover { color: var(--tenant-accent); }
[data-brand-secondary] .digichat-thread :focus-visible { outline-color: var(--brand-secondary); }
[data-brand-shape="pill"] .digichat-thread { --composer-radius: 1.75rem !important; }
[data-brand-shape="pill"] .digichat-thread :is(.aui-thread-welcome-suggestion, .aui-composer-send) { border-radius: 9999px; }
[data-brand-shape="pill"] .digichat-thread .aui-user-message-content-wrapper { border-radius: 1.25rem; }
[data-brand-shape="pill"] .digichat-thread .aui-composer-root > .border-hair { border-radius: 1.75rem; padding-inline: 0.5rem; }
.light[data-brand] .digichat-thread .aui-composer-root > .border-hair { background: #fff; }
`;
