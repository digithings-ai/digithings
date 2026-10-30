/**
 * Tenant corner radii: how round the composer and the suggestion chips are
 * (`radius` on an embed tenant row, `chrome.radius` in the deploy YAML), so a
 * tenant whose site uses pill-shaped controls can match it without a skin.
 *
 * Whole pixels only, 0..48, validated at parse time; nothing else reaches the
 * stylesheet. Unset keys leave the skin's own shape alone.
 */
import { z } from "zod";

const Px = z.number().int().min(0).max(48);

export const TenantRadiusSchema = z
  .object({
    /** The composer box (and the edit composer), via the skin's --composer-radius. */
    composer: Px.optional(),
    /** The welcome suggestion chips. */
    chip: Px.optional(),
  })
  .strict();

export type TenantRadius = z.infer<typeof TenantRadiusSchema>;

/** Validate a registry value; throws with `ctx` so a bad row fails loudly like `accent`. */
export function parseTenantRadius(raw: unknown, ctx: string): TenantRadius | undefined {
  if (raw === undefined) return undefined;
  const parsed = TenantRadiusSchema.safeParse(raw);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    throw new Error(`${ctx}: radius.${issue?.path.join(".") ?? ""} ${issue?.message ?? "is invalid"}`);
  }
  return parsed.data;
}

/**
 * Stylesheet text for the tenant's radii; "" when the tenant sets none.
 * `:root:root` outranks the skin stylesheets that (re)define --composer-radius
 * on inner scopes, and the descendant `*` reaches whichever scope the skin uses.
 */
export function tenantRadiusCss(radius: TenantRadius | null | undefined): string {
  if (!radius) return "";
  let css = "";
  if (radius.composer !== undefined) {
    css += `:root:root .dc-embed-shell,:root:root .dc-embed-shell *{--composer-radius:${radius.composer}px}`;
  }
  if (radius.chip !== undefined) {
    css += `:root:root .dc-embed-shell .aui-thread-welcome-suggestion{border-radius:${radius.chip}px}`;
  }
  return css;
}
