import { eq } from "drizzle-orm";
import { getDb } from "@/db";
import { tenants, userTenants } from "@/db/schema";

/**
 * Resolve tenant slug for an OIDC subject.
 * In production, requires Postgres or an explicit DIGICHAT_DEFAULT_TENANT_SLUG (no silent `default`).
 */
export async function tenantSlugForOidcSubject(sub: string): Promise<string> {
  const explicit =
    process.env.DIGICHAT_DEFAULT_TENANT_SLUG?.trim() ||
    process.env.DIGICHAT_BOOTSTRAP_TENANT_SLUG?.trim() ||
    "";
  const db = getDb();
  if (!db) {
    if (process.env.NODE_ENV === "production") {
      if (!explicit) {
        throw new Error(
          "DIGICHAT_DATABASE_URL or DIGICHAT_DEFAULT_TENANT_SLUG is required in production"
        );
      }
      return explicit;
    }
    return explicit || "default";
  }

  const row = await db
    .select({ slug: tenants.slug })
    .from(userTenants)
    .innerJoin(tenants, eq(userTenants.tenantId, tenants.id))
    .where(eq(userTenants.providerAccountId, sub))
    .limit(1);

  const slug = row[0]?.slug;
  if (slug) return slug;
  if (process.env.NODE_ENV === "production" && !explicit) {
    throw new Error(
      "No tenant mapping for this user; provision user_tenants or set DIGICHAT_DEFAULT_TENANT_SLUG"
    );
  }
  return explicit || "default";
}
