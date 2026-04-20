import { eq } from "drizzle-orm";
import { timingSafeEqual } from "node:crypto";
import bcrypt from "bcryptjs";
import { getDb } from "@/db";
import { apiKeys, tenants } from "@/db/schema";

export const MACHINE_KEY_PREFIX = "digi_live_";

function safeEqualStr(a: string, b: string): boolean {
  const ba = Buffer.from(a, "utf8");
  const bb = Buffer.from(b, "utf8");
  if (ba.length !== bb.length) return false;
  return timingSafeEqual(ba, bb);
}

/**
 * Validate machine credential: env bootstrap key, or hashed key in Postgres.
 */
export async function validateMachineApiKey(
  header: string | null
): Promise<{ tenantSlug: string } | null> {
  if (!header?.startsWith("Bearer ")) return null;
  const token = header.slice(7).trim();
  if (!token) return null;

  const bootstrap = process.env.DIGICHAT_BOOTSTRAP_API_KEY?.trim();
  if (bootstrap && safeEqualStr(token, bootstrap)) {
    const slug = process.env.DIGICHAT_BOOTSTRAP_TENANT_SLUG?.trim() || "default";
    return { tenantSlug: slug };
  }

  const db = getDb();
  if (!db || !token.startsWith(MACHINE_KEY_PREFIX)) return null;

  const prefix = token.slice(0, 20);
  const rows = await db
    .select({
      keyHash: apiKeys.keyHash,
      slug: tenants.slug,
    })
    .from(apiKeys)
    .innerJoin(tenants, eq(apiKeys.tenantId, tenants.id))
    .where(eq(apiKeys.keyPrefix, prefix));

  for (const row of rows) {
    if (await bcrypt.compare(token, row.keyHash)) {
      return { tenantSlug: row.slug };
    }
  }
  return null;
}
