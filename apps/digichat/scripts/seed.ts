/**
 * Seed default tenant. Run: DIGICHAT_DATABASE_URL=... npx tsx scripts/seed.ts
 */
import postgres from "postgres";
import { drizzle } from "drizzle-orm/postgres-js";
import { tenants } from "../src/db/schema";

const url = process.env.DIGICHAT_DATABASE_URL?.trim();
if (!url) {
  console.error("DIGICHAT_DATABASE_URL is required");
  process.exit(1);
}

const sql = postgres(url, { max: 1 });
const db = drizzle(sql);

async function main() {
  await db
    .insert(tenants)
    .values({ slug: "default", name: "Default tenant" })
    .onConflictDoNothing({ target: tenants.slug });
  console.log("Seed complete (default tenant).");
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => sql.end({ timeout: 5 }));
