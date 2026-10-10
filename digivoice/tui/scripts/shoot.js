// Headless capture for the digivoice TUI visual gate.
//
// Renders the real app (mountDigivoice) with opentui's test renderer at a fixed
// cell grid and prints the captured frame as JSON: cols, rows, and per-line
// spans with fg/bg. A companion renderer (scripts/capture.py) turns that JSON
// into a PNG. Screenshots are throwaway review artifacts, not repo files.
//
// The session is a deterministic stub, so a shot never depends on the machine's
// models, history or microphone: the layout and every screen are the real ones.
//
// Usage: bun scripts/shoot.js <cols> <rows> <screen> [out.json]
import { createTestRenderer } from "@opentui/core/testing"

import { FOOTER, mountDigivoice } from "../src/app.js"

const HOME_ROWS = [
  { action: "History", path: "/history", meta: "", kind: "dir", name: "History" },
  { action: "Settings", path: "/settings", meta: "", kind: "dir", name: "Settings" },
  { action: "System", path: "/system", meta: "", kind: "dir", name: "System" },
  { action: "Quit", path: "/quit", meta: "", kind: "dir", name: "Quit" },
]

const CONTEXT = ["▦ stt ggml-base.en · tts (auto)", "▥ right-option (toggle)", "■ ok (5/5 ready)"]

const SETTINGS_ROWS = [
  {
    action: "Dictation model",
    path: "/settings/dictation",
    meta: "ggml-base.en",
    kind: "pick",
    name: "dictation",
  },
  { action: "Rewrite", path: "/settings/rewrite", meta: "on", kind: "pick", name: "rewrite" },
  { action: "Speech voice", path: "/settings/speech", meta: "auto", kind: "pick", name: "speech" },
  {
    action: "Paste on stop",
    path: "/settings/paste",
    meta: "on",
    kind: "choice",
    name: "paste_on_stop",
  },
  {
    action: "Live banner",
    path: "/settings/banner",
    meta: "full (top-center)",
    kind: "choice",
    name: "live_banner",
  },
  { action: "Hotkeys", path: "/settings/hotkeys", meta: "", kind: "pick", name: "hotkeys" },
]

const SYSTEM_ROWS = [
  { action: "Doctor", path: "/doctor", meta: "", kind: "dir", name: "Doctor" },
  { action: "Logs", path: "/system/logs", meta: "", kind: "dir", name: "Logs" },
  { action: "Reload", path: "/reload", meta: "", kind: "dir", name: "Reload" },
  { action: "Reset", path: "/reset", meta: "", kind: "dir", name: "Reset" },
  { action: "Restart", path: "/restart", meta: "", kind: "dir", name: "Restart" },
  { action: "Update", path: "/update", meta: "", kind: "dir", name: "Update" },
]

const DOCTOR_ROWS = [
  { action: "whisper", meta: "ok", detail: "/opt/homebrew/bin/whisper-cli", path: "", kind: "check" },
  { action: "piper", meta: "ok", detail: "~/.local/bin/piper", path: "", kind: "check" },
  { action: "sox", meta: "missing", detail: "no sox or ffmpeg on PATH", path: "", kind: "check" },
  { action: "paths", meta: "ok", detail: "~/.local/share/digivoice", path: "", kind: "check" },
]

const HISTORY_ROWS = [
  {
    action: "2026-10-09T14:02:11Z",
    path: "/history",
    meta: "",
    text: "ship the incremental rail merge on develop",
    kind: "take",
    index: 0,
  },
  {
    action: "2026-10-09T13:58:03Z",
    path: "/history",
    meta: "",
    text: "walk the parity checklist screen by screen",
    kind: "take",
    index: 1,
  },
]

const SCREENS = {
  home: { start: "/", path: "/", title: "Actions", kind: "home", rows: HOME_ROWS, selected: 0 },
  settings: {
    start: "/settings",
    path: "/settings",
    title: "settings",
    kind: "settings",
    rows: SETTINGS_ROWS,
    selected: 0,
  },
  system: {
    start: "/system",
    path: "/system",
    title: "System",
    kind: "system",
    rows: SYSTEM_ROWS,
    selected: 0,
  },
  doctor: {
    start: "/doctor",
    path: "/doctor",
    title: "doctor",
    kind: "doctor",
    rows: DOCTOR_ROWS,
    selected: 0,
    ok: false,
  },
  history: {
    start: "/history",
    path: "/history",
    title: "/digivoice/history",
    kind: "history",
    rows: HISTORY_ROWS,
    selected: 0,
    page: 1,
    pages: 1,
    paging: false,
  },
}

const [, , colsArg, rowsArg, screenArg, outArg] = process.argv
const cols = Number(colsArg) || 80
const rows = Number(rowsArg) || 24
const name = screenArg || "home"
const spec = SCREENS[name] || SCREENS.home

function stubSession(screen) {
  return {
    calls: [],
    call(request) {
      this.calls.push(request)
      switch (request.op) {
        case "boot":
          return {
            footer: FOOTER,
            context: CONTEXT,
            status: "",
            start: screen.start,
            home: HOME_ROWS,
            screen: {
              title: screen.title,
              path: screen.path,
              rows: screen.rows,
              selected: screen.selected,
              page: screen.page,
              pages: screen.pages,
              paging: screen.paging,
              ok: screen.ok,
            },
          }
        case "quit":
          return { exit: 0, stopped: true }
        case "close":
          return { exit: 0, stopped: false }
        default:
          return { rows: screen.rows }
      }
    },
    follow() {
      return { cancel() {} }
    },
  }
}

const setup = await createTestRenderer({ width: cols, height: rows })
const app = mountDigivoice(setup.renderer, stubSession(spec), {
  truecolor: true,
  cols,
  tMs: 1_000_000_000,
  animate: false,
  start: spec.start,
})
// The app boots asynchronously (openBoot awaits the session), so render a few
// frames with a short gap until the pane paints. A single renderOnce() captures
// the pre-boot frame (hero + empty rail only).
await setup.renderOnce()
for (let i = 0; i < 40; i += 1) {
  await new Promise((resolve) => setTimeout(resolve, 10))
  await setup.renderOnce()
}

const frame = setup.captureSpans()
const json = JSON.stringify({
  cols: frame.cols,
  rows: frame.rows,
  lines: frame.lines.map((line) =>
    line.spans.map((span) => ({
      text: span.text,
      fg: span.fg ? span.fg.toInts() : null,
      bg: span.bg ? span.bg.toInts() : null,
      attributes: span.attributes ?? 0,
    })),
  ),
})

if (outArg) await Bun.write(outArg, json)
else console.log(json)

app.destroy()
setup.renderer.destroy()
process.exit(0)
