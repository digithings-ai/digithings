export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  // Fail closed on invalid digichat.yaml / DIGICHAT_EMBED_TENANTS before serving.
  const { initDigichatConfigAtStartup } = await import(
    "@/lib/deploy-config/loader"
  );
  initDigichatConfigAtStartup();
  // Customer-license verification: pure local crypto, never touches the
  // network, never throws (fail-open). Must run before the AUTO_MIGRATE
  // early-return below, which is the common-case exit.
  const { initLicenseStateAtStartup } = await import("@/lib/license/state");
  initLicenseStateAtStartup();
  // 24h heartbeat sender: schedules timers and fires one attempt
  // fire-and-forget. Unlicensed containers never start a timer.
  const { startLicenseHeartbeat } = await import("@/lib/license/heartbeat");
  startLicenseHeartbeat();
  if (process.env.DIGICHAT_AUTO_MIGRATE !== "1") return;
  const { runMigrate } = await import("@/lib/migrate");
  await runMigrate();
}
