import assert from "node:assert/strict"
import test from "node:test"

import { createTestRenderer } from "@opentui/core/testing"

import { FOOTER, mountDigivoice, onHangup } from "../src/app.js"
import { BUILD_MS, SHADES, letterGap, wordmarkLines } from "../src/hero.js"

const HOME_ROWS = [
  { action: "History", path: "/history", meta: "", kind: "dir", name: "History" },
  { action: "Settings", path: "/settings", meta: "", kind: "dir", name: "Settings" },
  { action: "System", path: "/system", meta: "", kind: "dir", name: "System" },
  { action: "Quit", path: "/quit", meta: "", kind: "dir", name: "Quit" },
]

function session(extra = {}) {
  const calls = []
  return {
    calls,
    call(request) {
      calls.push(request)
      if (extra[request.op]) return extra[request.op](request)
      if (request.op === "boot") {
        return {
          footer: FOOTER,
          context: ["▦ stt ggml-base.en"],
          start: "/",
          home: HOME_ROWS,
          screen: { title: "Actions", path: "/", rows: HOME_ROWS },
        }
      }
      if (request.op === "quit") return { exit: 0, stopped: true }
      if (request.op === "close") return { exit: 0, stopped: false }
      if (request.op === "rows") {
        return {
          path: request.path,
          rows: [
            {
              action: "Tiny",
              path: `${request.path}/ggml-tiny.en`,
              meta: "English · ~75 MB",
              kind: "choice",
              name: "Tiny",
            },
          ],
        }
      }
      if (request.op === "system") {
        return {
          title: "System",
          path: "/system",
          rows: [
            { action: "Doctor", path: "/doctor", meta: "", kind: "dir", name: "Doctor" },
            { action: "Logs", path: "/system/logs", meta: "", kind: "dir", name: "Logs" },
          ],
        }
      }
      return { rows: [] }
    },
  }
}

test("wordmark is five rows with gap 2 and one color mode", () => {
  assert.equal(letterGap(120, 9), 2)
  const cube = wordmarkLines("DIGIVOICE", { cols: 120, tMs: BUILD_MS, truecolor: false })
  const rgb = wordmarkLines("DIGIVOICE", { cols: 120, tMs: BUILD_MS, truecolor: true })
  assert.equal(cube.rows, 5)
  assert.equal(cube.gap, 2)
  const drawn = cube.lines.flat().map((cell) => cell.ch).join("")
  assert.match(drawn, /[█▀▄]/)
  for (const cell of cube.lines.flat()) {
    if (!cell.color) continue
    assert.equal(cell.color.rgb, undefined)
    assert.ok(SHADES.some((shade) => shade.cube === cell.color.cube))
  }
  for (const cell of rgb.lines.flat()) {
    if (!cell.color) continue
    assert.equal(cell.color.cube, undefined)
    assert.ok(SHADES.some((shade) => shade.rgb === cell.color.rgb))
  }
  const early = wordmarkLines("DIGIVOICE", { cols: 120, tMs: 200, truecolor: false })
  const earlyOn = early.lines.flat().filter((cell) => cell.ch !== " ").length
  const fullOn = cube.lines.flat().filter((cell) => cell.ch !== " ").length
  assert.ok(earlyOn < fullOn)
})

test("home shows the footer and selection, and esc does not quit", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session()
  try {
    const app = mountDigivoice(setup.renderer, api, {
      truecolor: false,
      tMs: BUILD_MS,
      animate: false,
      cols: 100,
    })
    const frame = await setup.waitForFrame((value) => value.includes("History") && value.includes(FOOTER))
    assert.match(frame, /\[\*\] History/)
    assert.match(frame, /\[ \] Settings/)
    const lines = frame.split("\n")
    const historyAt = lines.findIndex((line) => line.includes("[*] History"))
    assert.ok(historyAt > 4, "the hero sits above the menu, not on the first row")
    assert.ok(lines[historyAt + 1].includes("/history"))
    const settingsAt = lines.findIndex((line) => line.includes("[ ] Settings"))
    assert.ok(lines[settingsAt + 1].includes("/settings"))
    const glyphAt = lines.findIndex((line) => /[█▀▄]/.test(line))
    assert.ok(glyphAt > 0, "the wordmark is not pinned to the top row")
    assert.doesNotMatch(frame, /teal|waveform/i)
    setup.mockInput.pressArrow("down")
    await setup.renderOnce()
    assert.match(setup.captureCharFrame(), /\[\*\] Settings/)
    setup.mockInput.pressEscape()
    assert.equal(await app.done, 0)
    assert.equal(app.exitCode, 0)
    assert.ok(!api.calls.some((call) => call.op === "quit"))
    assert.ok(api.calls.some((call) => call.op === "close"))
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("a click opens settings", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session()
  try {
    const app = mountDigivoice(setup.renderer, api, {
      truecolor: true,
      tMs: BUILD_MS,
      animate: false,
      cols: 100,
    })
    await setup.waitForFrame((value) => value.includes("[*] History"))
    const lines = setup.captureCharFrame().split("\n")
    const settingsRow = lines.findIndex((line) => line.includes("Settings"))
    assert.ok(settingsRow >= 0)
    const settingsCol = lines[settingsRow].indexOf("Settings")
    await setup.mockMouse.click(settingsCol, settingsRow)
    await setup.waitForFrame((value) => value.includes("Tiny") && value.includes("English"))
    assert.equal((setup.captureCharFrame().match(/English/g) || []).length, 1)
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("enter on quit asks the bridge to stop", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session()
  try {
    const app = mountDigivoice(setup.renderer, api, {
      truecolor: false,
      tMs: BUILD_MS,
      animate: false,
      cols: 100,
    })
    await setup.waitForFrame((value) => value.includes("[*] History"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    assert.equal(await app.done, 0)
    assert.ok(api.calls.some((call) => call.op === "quit"))
    assert.ok(!api.calls.some((call) => call.op === "close"))
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

const SPEECH_ROWS = [
  { action: "model", path: "/settings/speech/model", meta: "", kind: "pick", name: "model" },
  { action: "voice", path: "/settings/speech/voice", meta: "", kind: "pick", name: "voice" },
  { action: "paste", path: "/settings/speech/paste", meta: "on", kind: "pick", name: "paste" },
]

test("a settings choice returns to the same row", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session({
    rows(request) {
      if (request.path === "/settings") {
        return {
          path: request.path,
          rows: [{ action: "speech", path: "/settings/speech", meta: "", kind: "dir", name: "speech" }],
        }
      }
      if (request.path === "/settings/speech") {
        return { path: request.path, rows: SPEECH_ROWS }
      }
      if (request.path === "/settings/speech/paste") {
        return {
          path: request.path,
          rows: [
            { action: "on", path: "/settings/speech/paste/on", meta: "", kind: "choice", name: "on" },
            { action: "off", path: "/settings/speech/paste/off", meta: "", kind: "choice", name: "off" },
          ],
        }
      }
      return { path: request.path, rows: [] }
    },
    apply() {
      return { saved: true, path: "/settings/speech", rows: SPEECH_ROWS }
    },
  })
  try {
    const app = mountDigivoice(setup.renderer, api, {
      truecolor: false,
      tMs: BUILD_MS,
      animate: false,
      cols: 100,
    })
    await setup.waitForFrame((value) => value.includes("[*] History"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("speech"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("paste"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("[*] on"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("[*] paste"))
    assert.match(setup.captureCharFrame(), /\[\*\] paste/)
    assert.doesNotMatch(setup.captureCharFrame(), /\[\*\] model/)
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("esc from a download confirm returns to that model", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session({
    rows(request) {
      if (request.path === "/settings/speech/model") {
        return {
          path: request.path,
          rows: [
            {
              action: "Tiny",
              path: "/settings/speech/model/ggml-tiny.en",
              meta: "English · ~75 MB",
              kind: "choice",
              name: "Tiny",
            },
          ],
        }
      }
      if (request.path === "/settings") {
        return {
          path: request.path,
          rows: [{ action: "speech", path: "/settings/speech", meta: "", kind: "dir", name: "speech" }],
        }
      }
      return {
        path: request.path,
        rows: [{ action: "model", path: "/settings/speech/model", meta: "", kind: "pick", name: "model" }],
      }
    },
    apply(request) {
      if (!request.confirm) {
        return {
          confirm: true,
          title: "Download",
          rows: [
            { action: "Download", path: request.path, meta: "", kind: "confirm" },
            { action: "Back", path: request.path, meta: "", kind: "back" },
          ],
        }
      }
      return { saved: true, path: "/settings/speech", rows: SPEECH_ROWS }
    },
  })
  try {
    const app = mountDigivoice(setup.renderer, api, {
      truecolor: false,
      tMs: BUILD_MS,
      animate: false,
      cols: 100,
    })
    await setup.waitForFrame((value) => value.includes("[*] History"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("speech"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("model"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("[*] Tiny"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("Download"))
    setup.mockInput.pressEscape()
    await new Promise((resolve) => setTimeout(resolve, 80))
    await setup.renderOnce()
    const frame = setup.captureCharFrame()
    assert.match(frame, /\[\*\] Tiny/)
    assert.equal((frame.match(/English/g) || []).length, 1)
    assert.ok(!api.calls.some((call) => call.confirm))
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("restart confirms before it asks to re-exec", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session({
    system() {
      return {
        title: "System",
        path: "/system",
        rows: [
          { action: "Restart", path: "/restart", meta: "", kind: "dir", name: "Restart" },
          { action: "Update", path: "/update", meta: "", kind: "dir", name: "Update" },
        ],
      }
    },
    restart() {
      return { restart: true }
    },
    update() {
      return { note: "digivoice update is not wired yet" }
    },
  })
  try {
    const app = mountDigivoice(setup.renderer, api, {
      truecolor: false,
      tMs: BUILD_MS,
      animate: false,
      cols: 100,
    })
    await setup.waitForFrame((value) => value.includes("[*] History"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("Update"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("not wired yet"))
    assert.match(setup.captureCharFrame(), /\[\*\] Update/)
    setup.mockInput.pressArrow("up")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("Back") && value.includes("[*] Restart"))
    assert.ok(!api.calls.some((call) => call.op === "restart"))
    setup.mockInput.pressEnter()
    assert.equal(await app.done, 0)
    assert.equal(app.restarting, true)
    assert.ok(api.calls.some((call) => call.op === "restart"))
    assert.ok(!api.calls.some((call) => call.op === "quit"))
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("history, settings, system, logs, and doctor keep the bracketed row", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session({
    history() {
      return {
        title: "History",
        path: "/history",
        paging: false,
        rows: [
          {
            action: "ship it",
            path: "/history",
            meta: "2026-10-02T12:00:00Z",
            kind: "take",
            index: 0,
          },
        ],
      }
    },
    doctor() {
      return {
        title: "Doctor",
        path: "/doctor",
        ok: true,
        rows: [{ action: "whisper-cli", path: "/doctor", meta: "ok", kind: "note" }],
      }
    },
    logs() {
      return {
        title: "Logs",
        path: "/system/logs",
        rows: [{ action: "ready", path: "/system/logs", meta: "", kind: "note" }],
      }
    },
    system() {
      return {
        title: "System",
        path: "/system",
        rows: [
          { action: "Doctor", path: "/doctor", meta: "", kind: "dir", name: "Doctor" },
          { action: "Logs", path: "/system/logs", meta: "", kind: "dir", name: "Logs" },
        ],
      }
    },
    rows(request) {
      return {
        path: request.path,
        rows: [
          {
            action: "speech",
            path: "/settings/speech",
            meta: "",
            kind: "dir",
            name: "speech",
          },
        ],
      }
    },
  })
  try {
    const app = mountDigivoice(setup.renderer, api, {
      truecolor: false,
      tMs: BUILD_MS,
      animate: false,
      cols: 100,
    })
    await setup.waitForFrame((value) => value.includes("[*] History"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("ship it"))
    let frame = setup.captureCharFrame()
    assert.match(frame, /\[\*\] ship it/)
    assert.match(frame, /\/history/)
    assert.match(frame, /2026-10-02T12:00:00Z/)
    setup.mockInput.pressEscape()
    await new Promise((resolve) => setTimeout(resolve, 80))
    await setup.renderOnce()
    await setup.waitForFrame((value) => value.includes("[*] History") && value.includes("/history"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("paste") || value.includes("speech"))
    frame = setup.captureCharFrame()
    assert.match(frame, /\[\*\] speech/)
    assert.match(frame, /\/settings\/speech/)
    setup.mockInput.pressEscape()
    await new Promise((resolve) => setTimeout(resolve, 80))
    await setup.renderOnce()
    await setup.waitForFrame((value) => value.includes("[ ] System"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("[*] Doctor"))
    frame = setup.captureCharFrame()
    assert.match(frame, /\[\*\] Doctor/)
    assert.match(frame, /\/doctor/)
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("whisper-cli"))
    frame = setup.captureCharFrame()
    assert.match(frame, /\[\*\] whisper-cli/)
    assert.match(frame, /\/doctor/)
    assert.match(frame, /\bok\b/)
    setup.mockInput.pressEscape()
    await new Promise((resolve) => setTimeout(resolve, 80))
    await setup.renderOnce()
    await setup.waitForFrame((value) => value.includes("Logs"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("ready"))
    frame = setup.captureCharFrame()
    assert.match(frame, /\[\*\] ready/)
    assert.match(frame, /\/system\/logs/)
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("SIGHUP closes without quitting", () => {
  const api = session()
  assert.equal(onHangup(api), 0)
  assert.deepEqual(
    api.calls.map((call) => call.op),
    ["close"],
  )
})
