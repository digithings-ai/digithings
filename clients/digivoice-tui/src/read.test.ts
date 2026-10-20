import { expect, test } from "bun:test";
import { cliArgv, parseDoctor, parseHistory, parseSetup, parseSettings, parseStatus } from "./read";

test("cliArgv defaults to the console script", () => {
  expect(cliArgv({})).toEqual(["digivoice"]);
});

test("cliArgv honours DIGIVOICE_BIN so the CLI can run from source", () => {
  expect(cliArgv({ DIGIVOICE_BIN: "python3 -m digivoice" })).toEqual(["python3", "-m", "digivoice"]);
  expect(cliArgv({ DIGIVOICE_BIN: "  " })).toEqual(["digivoice"]);
});

const SETUP_JSON = JSON.stringify({
  stt_model: "ggml-base.en",
  tts_voice: null,
  rewrite_enabled: false,
  rewrite_timeout_seconds: 30.0,
  paths: {
    data_dir: "/Users/x/Library/Application Support/digivoice",
    models_dir: "/Users/x/Library/Application Support/digivoice/models",
    recordings_dir: "/Users/x/Library/Application Support/digivoice/recordings",
    history_file: "/Users/x/Library/Application Support/digivoice/history.jsonl",
    settings_file: "/Users/x/Library/Application Support/digivoice/settings.json",
  },
  hotkeys: {
    dict_toggle: "Right Option (keycode 61) — start/stop digivoice dict --toggle",
    speak_selection: "Double-tap Left Option — digivoice speak --selection",
    cancel: "Esc while recording — discard the take",
  },
  presets: { email: "email", none: "none" },
  rewrite_model_hint: "set rewrite_model when rewrite_enabled",
  setup_menu: [
    "Models (STT / TTS / rewrite)",
    "Features (paste, banner)",
    "Hotkeys (docs)",
    "Hardware recommendations (#4939 hook)",
    "Review & save",
    "Doctor (run health checks)",
    "Quit",
  ],
  model_fields: [
    "stt_model",
    "tts_voice",
    "rewrite_enabled",
    "rewrite_preset",
    "rewrite_model",
    "rewrite_runner",
    "rewrite_auto_route",
    "rewrite_timeout_seconds",
  ],
  feature_fields: ["paste_on_stop", "live_banner", "banner_position", "banner_density", "banner_animations"],
  hardware_recommendations: {
    tiers: [{ tier: "default", model: "ggml-base.en", note: "Snappy push-to-talk default; ships as ggml-base.en.bin." }],
    pointer: "See epic #4939 / CHR-853 — full hardware-aware catalog not rebuilt here.",
  },
});

test("parseSetup reads settings, paths, menu, and hardware", () => {
  const payload = parseSetup(SETUP_JSON);
  expect(payload).not.toBeNull();
  if (!payload) return;
  expect(payload.settings.stt_model).toBe("ggml-base.en");
  expect(payload.settings.rewrite_enabled).toBe(false);
  expect(payload.settings.tts_voice).toBeNull();
  // meta keys are not settings
  expect(payload.settings.paths).toBeUndefined();
  expect(payload.settings.setup_menu).toBeUndefined();
  expect(payload.paths.settings_file).toContain("settings.json");
  expect(payload.hotkeys.dict_toggle).toContain("Right Option");
  expect(payload.setup_menu).toHaveLength(7);
  expect(payload.model_fields).toHaveLength(8);
  expect(payload.feature_fields).toHaveLength(5);
  expect(payload.hardware.tiers[0]?.model).toBe("ggml-base.en");
  expect(payload.hardware.pointer).toContain("#4939");
});

test("parseSetup rejects non-JSON", () => {
  expect(parseSetup("not json")).toBeNull();
});

test("parseDoctor reads checks and the result line", () => {
  const text = [
    "digivoice doctor",
    "",
    "[ok] whisper-cli  /opt/homebrew/bin/whisper-cli",
    "[missing] ffmpeg  not on PATH",
    "[info] rewrite    disabled",
    "",
    "result: ok",
  ].join("\n");
  const report = parseDoctor(text);
  expect(report.checks).toHaveLength(3);
  expect(report.checks[0]).toEqual({ status: "ok", id: "whisper-cli", detail: "/opt/homebrew/bin/whisper-cli" });
  expect(report.checks[1]?.status).toBe("missing");
  expect(report.ok).toBe(true);
});

test("parseDoctor reads a not-ready host", () => {
  const report = parseDoctor("[ok] sox  /opt/homebrew/bin/sox\nresult: not ready");
  expect(report.checks).toHaveLength(1);
  expect(report.ok).toBe(false);
});

test("parseHistory reads entries and counts", () => {
  const json = JSON.stringify({
    file: "/Users/x/history.jsonl",
    present: true,
    skipped: 0,
    count: 2,
    total: 2,
    entries: [
      { ts: "2026-09-30T12:00:00.000Z", kind: "dict", text: "hello world", wav: "/Users/x/recordings/a.wav" },
      { ts: "2026-09-30T12:01:00.000Z", kind: "speak", text: "hi", wav: null },
    ],
  });
  const hist = parseHistory(json);
  expect(hist.present).toBe(true);
  expect(hist.count).toBe(2);
  expect(hist.entries[1]).toEqual({ ts: "2026-09-30T12:01:00.000Z", kind: "speak", text: "hi", wav: null });
});

test("parseHistory tolerates an empty payload", () => {
  const hist = parseHistory("{}");
  expect(hist.entries).toEqual([]);
  expect(hist.present).toBe(false);
});

test("parseStatus reads a snapshot and rejects an absent one", () => {
  const json = JSON.stringify({
    session: "abc",
    kind: "dict",
    state: "recording",
    text: "",
    detail: "",
    updated_ms: 123,
    pid: 42,
  });
  const snap = parseStatus(json);
  expect(snap?.state).toBe("recording");
  expect(snap?.pid).toBe(42);
  expect(parseStatus("no status yet")).toBeNull();
  expect(parseStatus('{"kind":"dict"}')).toBeNull();
});

test("parseSettings reads the public settings object", () => {
  expect(parseSettings('{"paste_on_stop":true}')).toEqual({ paste_on_stop: true });
  expect(parseSettings("nope")).toBeNull();
});
