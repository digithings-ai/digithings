/**
 * Deterministic stand-in for the digivoice CLI, so a recorded frame never
 * depends on a live backend (DIG-2698, ADR D7: recorded frames, not live
 * sockets).
 *
 * The exporter points the client at this script through DIGIVOICE_BIN. The
 * client resolves its CLI prefix when it spawns (`src/read.ts`), so setting
 * DIGIVOICE_BIN before the app module loads is enough.
 */
const SETUP = {
  settings: {
    stt_model: "ggml-base.en",
    tts_voice: "auto",
    rewrite_enabled: true,
    rewrite_preset: "email",
    rewrite_model: "llama3.2",
    rewrite_runner: "auto",
    rewrite_auto_route: true,
    rewrite_timeout_seconds: 30,
    paste_on_stop: true,
    live_banner: true,
    banner_position: "top-center",
    banner_density: "peek",
    banner_animations: true,
  },
  paths: {
    data_dir: "/tmp/digivoice",
    models_dir: "/tmp/digivoice/models",
    recordings_dir: "/tmp/digivoice/recordings",
    history_file: "/tmp/digivoice/history.jsonl",
    settings_file: "/tmp/digivoice/settings.json",
  },
  hotkeys: { dict_toggle: "right-option", speak_selection: "right-option+s", cancel: "escape" },
  presets: { email: "professional email", sms: "short text" },
  rewrite_model_hint: "llama3.2",
  setup_menu: ["Models (STT / TTS / rewrite)", "Features (paste, banner)", "Hotkeys (docs)", "Hardware recommendations", "Review & save", "Doctor (run health checks)", "Quit"],
  model_fields: ["stt_model", "tts_voice", "rewrite_enabled", "rewrite_preset", "rewrite_model", "rewrite_runner", "rewrite_auto_route", "rewrite_timeout_seconds"],
  feature_fields: ["paste_on_stop", "live_banner", "banner_position", "banner_density", "banner_animations"],
  hardware_recommendations: {
    tiers: [{ tier: "cpu", model: "ggml-base.en", note: "default" }],
    pointer: "see epic #4939",
  },
};

const args = process.argv.slice(2);

if (args[0] === "setup" && args.includes("--json")) {
  process.stdout.write(JSON.stringify(SETUP));
  process.exit(0);
}

if (args[0] === "doctor") {
  process.stdout.write("[ok] digivoice  /tmp/digivoice\nresult: ok\n");
  process.exit(0);
}

if (args[0] === "history" && args.includes("--json")) {
  process.stdout.write(
    JSON.stringify({ file: "/tmp/digivoice/history.jsonl", present: true, count: 1, total: 1, entries: [{ ts: "2026-10-22T00:00:00Z", kind: "note", text: "hello", wav: null }] }),
  );
  process.exit(0);
}

if (args[0] === "status") {
  process.stdout.write(JSON.stringify({ session: "s", kind: "idle", state: "idle", text: "ready", detail: "", updated_ms: 0, pid: 1 }));
  process.exit(0);
}

if (args[0] === "settings" && args.includes("--json")) {
  process.stdout.write(JSON.stringify(SETUP.settings));
  process.exit(0);
}

process.stderr.write(`unknown command: ${args.join(" ")}\n`);
process.exit(1);