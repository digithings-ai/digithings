/**
 * Tenant colours: a light and a dark colour set for one tenant's chat
 * (`chrome.colors` in the deploy YAML, `colors` on an embed tenant row).
 *
 * A named palette (`palette:`) picks one of the design kit's palettes and is
 * refused on embeds, because the embed pins its own document theme. A tenant
 * that has to match its own site needs its own hexes instead, per mode. This
 * module is that hook: validated `#rrggbb` values only (never a URL, a
 * `var()` or free CSS), turned into custom properties for the mode the
 * document is painting. Each set is optional and each key in it is optional:
 * an unset key keeps the skin's own value.
 *
 * The CSS is rendered server-side by the embed route shell, so the tenant's
 * canvas is right from the first parsed byte. The selectors double `:root`
 * so they beat palettes.css (`:root[data-palette][data-theme]`) and the
 * shadcn `.dark` wrapper without `!important`.
 *
 * The tenant's colours are its default look only. A palette the visitor picks
 * with `/theme` paints `data-palette` on the root, and the root selector here
 * requires its absence, so every palette re-themes a tenant chat in full.
 */
import { z } from "zod";
import { HEX_COLOR } from "@/lib/hex-color";

const Hex = z.string().regex(HEX_COLOR, "must be #rrggbb hex");

export const TenantColorSetSchema = z
  .object({
    /** Page and thread canvas. */
    background: Hex.optional(),
    /** Raised surfaces: the composer, cards, menus. */
    surface: Hex.optional(),
    /** Body text. */
    text: Hex.optional(),
    /** Secondary text: hints, timestamps, the action bar. */
    muted: Hex.optional(),
    /** Hairlines and input borders. */
    border: Hex.optional(),
    /** Accent fill (send button, chips) and the text drawn on it. */
    accent: Hex.optional(),
    onAccent: Hex.optional(),
    /** Inline links in answers. Kept apart from the accent so a bright brand fill can sit next to an AA link colour. */
    link: Hex.optional(),
    /** The visitor's message bubble and its text. */
    userBubble: Hex.optional(),
    userBubbleText: Hex.optional(),
    /** Keyboard focus ring. */
    focusRing: Hex.optional(),
  })
  .strict();

export const TenantColorsSchema = z
  .object({ light: TenantColorSetSchema.optional(), dark: TenantColorSetSchema.optional() })
  .strict();

export type TenantColorSet = z.infer<typeof TenantColorSetSchema>;
export type TenantColors = z.infer<typeof TenantColorsSchema>;

/** Validate a registry value; throws with `ctx` so a bad row fails loudly like `accent`. */
export function parseTenantColors(raw: unknown, ctx: string): TenantColors | undefined {
  if (raw === undefined) return undefined;
  const parsed = TenantColorsSchema.safeParse(raw);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    throw new Error(`${ctx}: colors.${issue?.path.join(".") ?? ""} ${issue?.message ?? "is invalid"}`);
  }
  return parsed.data;
}

/** Custom properties for one set, in a stable order. Values are validated hex only. */
export function tenantColorVars(set: TenantColorSet): [string, string][] {
  const out: [string, string][] = [];
  const add = (names: string[], value: string | undefined) => {
    if (value) for (const n of names) out.push([n, value]);
  };
  add(["--bg", "--embed-canvas", "--background", "--term-bg", "--chat-skin-canvas"], set.background);
  add(["--surface", "--surface-2", "--card", "--popover", "--composer-bg", "--term-fill"], set.surface);
  add(["--ink", "--ink-soft", "--foreground", "--card-foreground", "--popover-foreground", "--term-ink"], set.text);
  add(["--ink-mute", "--muted-foreground", "--term-mute"], set.muted);
  add(["--hair", "--hair-2", "--border", "--input", "--term-hair"], set.border);
  add(["--accent", "--tenant-accent", "--primary"], set.accent);
  add(["--on-accent", "--accent-foreground", "--primary-foreground"], set.onAccent);
  add(["--tenant-link"], set.link);
  add(["--tenant-user-bubble"], set.userBubble);
  add(["--tenant-user-bubble-text"], set.userBubbleText);
  add(["--ring", "--tenant-focus-ring"], set.focusRing);
  return out;
}

function modeCss(mode: "light" | "dark", set: TenantColorSet): string {
  const vars = tenantColorVars(set);
  if (!vars.length) return "";
  const root = `:root:root[data-theme="${mode}"]:not([data-palette])`;
  const scopes = [
    root,
    `${root} .dc-embed-shell`,
    `${root} .dc-embed-shell .dark`,
    `${root} .digichat-thread`,
    `${root} [data-stock-product]`,
  ].join(",");
  let css = `${scopes}{${vars.map(([k, v]) => `${k}:${v}`).join(";")}}`;
  if (set.background) css += `${root} body{background:${set.background}}`;
  if (set.link) css += `${root} .aui-md-a{color:var(--tenant-link)}`;
  if (set.userBubble || set.userBubbleText) {
    css += `${root} .aui-user-message-content{${set.userBubble ? "background:var(--tenant-user-bubble);" : ""}${set.userBubbleText ? "color:var(--tenant-user-bubble-text)" : ""}}`;
  }
  if (set.focusRing) css += `${root} :focus-visible{outline-color:var(--tenant-focus-ring)}`;
  return css;
}

/** Stylesheet text for the tenant's colours; "" when the tenant sets none. */
export function tenantColorsCss(colors: TenantColors | null | undefined): string {
  if (!colors) return "";
  return (colors.light ? modeCss("light", colors.light) : "") + (colors.dark ? modeCss("dark", colors.dark) : "");
}
