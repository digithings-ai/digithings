/**
 * Tenant fonts: a heading and a body face for one tenant's chat
 * (`chrome.fonts` in the deploy YAML, `fonts` on an embed tenant row).
 *
 * Fonts only, as CSS custom properties (plus `font-family` reading them) on
 * the chat wrapper: no rules, no
 * shapes, no colours. The faces are self-hosted with next/font in the
 * (digichat) root layout, so the CSP's `font-src 'self'` holds: a tenant names
 * a font from TENANT_FONTS, never a URL. Adding a font is one next/font call in
 * that layout plus one entry here.
 *
 * The variables are the design kit's own (`--font-sans-face`, `--font-sans`,
 * `--font-heading`, `--font-display`). A skin that reads them takes the face;
 * a skin that pins its own face (the mono digichat skin) keeps it.
 */
import type { CSSProperties } from "react";
import { z } from "zod";

/** Font id → the CSS variable next/font sets on <html> for it. */
export const TENANT_FONTS = {
  cabin: "--font-brand-cabin",
  mulish: "--font-brand-mulish",
} as const;

export type TenantFontId = keyof typeof TENANT_FONTS;
const TENANT_FONT_IDS = Object.keys(TENANT_FONTS) as [TenantFontId, ...TenantFontId[]];

export const TenantFontsSchema = z
  .object({
    heading: z.enum(TENANT_FONT_IDS).optional(),
    body: z.enum(TENANT_FONT_IDS).optional(),
    /** Weight of the welcome title and markdown headings (a tenant's site headings are often bolder than the skin's 500). */
    headingWeight: z.union([z.literal(400), z.literal(500), z.literal(600), z.literal(700)]).optional(),
  })
  .strict();

export type TenantFonts = z.infer<typeof TenantFontsSchema>;

/** Validate a registry value; throws with `ctx` so a bad row fails loudly like `accent`. */
export function parseTenantFonts(raw: unknown, ctx: string): TenantFonts | undefined {
  if (raw === undefined) return undefined;
  const parsed = TenantFontsSchema.safeParse(raw);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    throw new Error(`${ctx}: fonts.${issue?.path.join(".") ?? ""} ${issue?.message ?? "is invalid"}`);
  }
  return parsed.data;
}

function stack(id: TenantFontId): string {
  return `var(${TENANT_FONTS[id]}), ui-sans-serif, system-ui, sans-serif`;
}

/** Inline font style for the chat wrapper; undefined when the tenant sets none. */
export function tenantFontStyle(fonts: TenantFonts | null | undefined): CSSProperties | undefined {
  if (!fonts) return undefined;
  const style: Record<string, string> = {};
  if (fonts.body) {
    style["--font-sans-face"] = `var(${TENANT_FONTS[fonts.body]})`;
    style["--font-sans"] = stack(fonts.body);
    style["--font-family"] = stack(fonts.body);
    // The page body pins Inter by class (next/font), so a variable alone never
    // reaches the catalog skins: the wrapper re-reads it. A skin that sets its
    // own face (digichat's mono) still wins inside its scope.
    style.fontFamily = "var(--font-sans)";
  }
  if (fonts.heading) {
    style["--font-heading"] = stack(fonts.heading);
    style["--font-display"] = stack(fonts.heading);
  }
  return Object.keys(style).length ? (style as CSSProperties) : undefined;
}

/**
 * The one rule tenant fonts add. Stock skins draw the welcome title and
 * markdown headings in the body face (`font-sans`) at the skin's weight, so a
 * tenant heading face set only as `--font-heading` never reached them. Scoped
 * to the wrapper that carries `data-tenant-heading-font`, which the embed sets
 * only when the tenant names a heading face or weight: neither, no rule.
 */
const TENANT_HEADING_SELECTOR =
  "[data-tenant-heading-font] :is(.aui-thread-welcome-message-inner,.aui-md-h1,.aui-md-h2,.aui-md-h3,.aui-md-h4)";

/** Whether the tenant's fonts need the heading rule (and the wrapper attribute). */
export function hasTenantHeadingRule(fonts: TenantFonts | null | undefined): boolean {
  return Boolean(fonts?.heading || fonts?.headingWeight);
}

/** The heading rule for these fonts; "" when the tenant sets no heading face or weight. */
export function tenantHeadingFontCss(fonts: TenantFonts | null | undefined): string {
  if (!fonts || !hasTenantHeadingRule(fonts)) return "";
  const decls: string[] = [];
  if (fonts.heading) decls.push("font-family:var(--font-heading)");
  if (fonts.headingWeight) decls.push(`font-weight:${fonts.headingWeight}`);
  return `${TENANT_HEADING_SELECTOR}{${decls.join(";")}}`;
}
