export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  if (process.env.DIGICHAT_AUTO_MIGRATE !== "1") return;
  const { runMigrate } = await import("@/lib/migrate");
  await runMigrate();
}
