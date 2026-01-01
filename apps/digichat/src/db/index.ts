import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

let client: postgres.Sql | null = null;
let db: ReturnType<typeof drizzle<typeof schema>> | null = null;

export function getDb() {
  const url = process.env.DIGICHAT_DATABASE_URL?.trim();
  if (!url) return null;
  if (!client) {
    client = postgres(url, { max: 10, idle_timeout: 20, connect_timeout: 10 });
    db = drizzle(client, { schema });
  }
  return db;
}

export async function closeDb() {
  if (client) {
    await client.end({ timeout: 5 });
    client = null;
    db = null;
  }
}

export { schema };
