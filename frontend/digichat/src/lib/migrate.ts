import { drizzle } from "drizzle-orm/postgres-js";
import { migrate } from "drizzle-orm/postgres-js/migrator";
import postgres from "postgres";
import path from "node:path";

/**
 * Apply Drizzle migrations (Postgres). No-op when DIGICHAT_DATABASE_URL is unset.
 */
export async function runMigrate(): Promise<void> {
  const url = process.env.DIGICHAT_DATABASE_URL?.trim();
  if (!url) return;

  const sql = postgres(url, { max: 1 });
  try {
    const db = drizzle(sql);
    const folder = path.join(process.cwd(), "drizzle");
    await migrate(db, { migrationsFolder: folder });
  } finally {
    await sql.end({ timeout: 5 });
  }
}
