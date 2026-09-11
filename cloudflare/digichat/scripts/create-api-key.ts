/**
 * Issue a machine API key for a tenant slug. Prints the key once.
 * DIGICHAT_DATABASE_URL=... npx tsx scripts/create-api-key.ts [tenantSlug] [label]
 */
import { randomBytes } from "node:crypto";
import { eq } from "drizzle-orm";
import postgres from "postgres";
import { drizzle } from "drizzle-orm/postgres-js";
import bcrypt from "bcryptjs";
import { apiKeys, tenants } from "../src/db/schema";
import { MACHINE_KEY_PREFIX } from "../src/lib/api-key";

const url = process.env.DIGICHAT_DATABASE_URL?.trim();
if (!url) {
  console.error("DIGICHAT_DATABASE_URL is required");
  process.exit(1);
}

const tenantSlug = process.argv[2] ?? "default";
const label = process.argv[3] ?? "cli";

const sql = postgres(url, { max: 1 });
const db = drizzle(sql);

async function main() {
  const t = await db.select().from(tenants).where(eq(tenants.slug, tenantSlug)).limit(1);
  if (!t[0]) {
    console.error(`Unknown tenant slug: ${tenantSlug}. Run npm run db:seed first.`);
    process.exit(1);
  }

  const raw = MACHINE_KEY_PREFIX + randomBytes(24).toString("base64url");
  const keyPrefix = raw.slice(0, 20);
  const keyHash = await bcrypt.hash(raw, 12);

  await db.insert(apiKeys).values({
    tenantId: t[0].id,
    keyHash,
    keyPrefix,
    label,
  });

  console.log("\nSave this secret (shown once):\n");
  console.log(raw);
  console.log("\nUse: Authorization: Bearer " + raw + "\n");
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => sql.end({ timeout: 5 }));
