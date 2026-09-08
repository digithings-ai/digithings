export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  // Fail closed on invalid digichat.yaml / DIGICHAT_EMBED_TENANTS before serving.
  const { initDigichatConfigAtStartup } = await import(
    "@/lib/deploy-config/loader"
  );
  initDigichatConfigAtStartup();
  if (process.env.DIGICHAT_AUTO_MIGRATE !== "1") return;
  const { runMigrate } = await import("@/lib/migrate");
  await runMigrate();
}
