import assert from "node:assert/strict"
import test from "node:test"

import { createTestRenderer } from "@opentui/core/testing"

import { FOOTER, mountDigivoice, onHangup, optionBinding } from "../src/app.js"
import { BUILD_MS, SHADES, letterGap, wordmarkLines } from "../src/hero.js"

const HOME_ROWS = [
  { action: "History", path: "/history", meta: "", kind: "dir", name: "History" },
  { action: "Settings", path: "/settings", meta: "", kind: "dir", name: "Settings" },
  { action: "System", path: "/system", meta: "", kind: "dir", name: "System" },
  { action: "Quit", path: "/quit", meta: "", kind: "dir", name: "Quit" },
]

const STATUS = "ggml-base.en · paste · ok"

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
          status: STATUS,
          start: "/",
          home: HOME_ROWS,
          screen: { title: "Actions", path: "/", rows: HOME_ROWS },
        }
      }
      if (request.op === "quit") return { exit: 0, stopped: true }
      if (request.op === "close") return { exit: 0, stopped: false }
      if (request.op === "save") return { saved: true }
      if (request.op === "reload") return { note: "reloaded" }
      if (request.op === "reset") return { note: "settings reset" }
      if (request.op === "restart") return { restart: true }
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

function mount(setup, api, extra = {}) {
  return mountDigivoice(setup.renderer, api, {
    truecolor: false,
    tMs: BUILD_MS,
    animate: false,
    cols: 100,
    ...extra,
  })
}

async function settle(setup) {
  await new Promise((resolve) => setTimeout(resolve, 80))
  await setup.renderOnce()
}

test("a physical option press fills a binding the adapter can arm", () => {
  assert.equal(optionBinding({ name: "option" }), "Right Option")
  assert.equal(optionBinding({ name: "alt" }), "Right Option")
  assert.equal(optionBinding({ name: "", option: true }), "Right Option")
  assert.equal(optionBinding({ name: "option", keycode: 58 }), "Left Option")
  assert.equal(optionBinding({ name: "option", code: "AltRight" }), "Right Option")
  assert.equal(optionBinding({ name: "a", option: true, ctrl: true }), "")
})

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

test("home pins the hero and esc does not quit", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session()
  try {
    const app = mount(setup, api)
    const frame = await setup.waitForFrame(
      (value) => value.includes("│ /history") && value.includes(FOOTER) && value.includes(STATUS),
    )
    const lines = frame.split("\n")
    assert.equal(lines.findIndex((line) => /[█▀▄]/.test(line)), 0)
    const statusAt = lines.findIndex((line) => line.includes("ggml-base.en"))
    assert.equal(statusAt, 6)
    assert.match(frame, /\/digivoice/)
    assert.match(frame, /\/settings/)
    assert.match(frame, /\/system/)
    assert.match(frame, /\/quit/)
    assert.doesNotMatch(frame, /History/)
    assert.doesNotMatch(frame, /\[\*\]|\[ \]/)
    const historyAt = lines.findIndex((line) => line.includes("│ /history"))
    assert.equal((lines[historyAt].match(/\/history/g) || []).length, 1)
    const footerAt = lines.findIndex((line) => line.includes(FOOTER))
    assert.ok(footerAt > 40, "the footer stays at the bottom")
    assert.ok(footerAt > historyAt)
    const pathCol = (token) => lines.find((line) => line.includes(token)).indexOf(token)
    assert.equal(pathCol("/history"), pathCol("/quit"))
    assert.equal(lines[historyAt][pathCol("/history") - 2], "│")
    const quitLine = lines.find((line) => line.includes("/quit"))
    assert.equal(quitLine[pathCol("/quit") - 2], " ")
    const heroCol = lines.find((line) => /[█▀▄]/.test(line)).search(/\S/)
    assert.ok(heroCol > pathCol("/history") - 2)
    setup.mockInput.pressArrow("down")
    await setup.renderOnce()
    assert.match(setup.captureCharFrame(), /│ \/settings/)
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
    const app = mount(setup, api, { truecolor: true })
    await setup.waitForFrame((value) => value.includes("│ /history"))
    const lines = setup.captureCharFrame().split("\n")
    const settingsRow = lines.findIndex((line) => line.includes("/settings"))
    assert.ok(settingsRow >= 0)
    const settingsCol = lines[settingsRow].indexOf("/settings")
    setup.mockMouse.moveTo(settingsCol, settingsRow)
    await setup.renderOnce()
    const hovered = setup.captureCharFrame().split("\n")[settingsRow]
    assert.ok(hovered.includes("│"), "hover uses the selection bar")
    assert.ok(hovered.includes("/settings"))
    await setup.mockMouse.click(settingsCol, settingsRow)
    await setup.waitForFrame((value) => value.includes("Tiny") && value.includes("English"))
    const picked = setup.captureCharFrame()
    assert.equal((picked.match(/English/g) || []).length, 1)
    const tiny = picked.split("\n").find((line) => line.includes("Tiny"))
    assert.ok(tiny.includes("English"))
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("enter on quit asks the bridge to stop", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session()
  try {
    const app = mount(setup, api)
    await setup.waitForFrame((value) => value.includes("│ /history"))
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
    const app = mount(setup, api)
    await setup.waitForFrame((value) => value.includes("│ /history"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("/speech"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("/paste"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("│ /on"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("│ /paste"))
    const frame = setup.captureCharFrame()
    assert.match(frame, /│ \/paste/)
    assert.match(frame, /on/)
    assert.doesNotMatch(frame, /│ \/model/)
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
    const app = mount(setup, api)
    await setup.waitForFrame((value) => value.includes("│ /history"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("/speech"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("/model"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("│ Tiny"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("Download"))
    setup.mockInput.pressEscape()
    await settle(setup)
    const frame = setup.captureCharFrame()
    assert.match(frame, /│ Tiny/)
    assert.equal((frame.match(/English/g) || []).length, 1)
    assert.ok(!api.calls.some((call) => call.confirm))
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("leaving settings writes settings before the screen changes", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session({
    rows(request) {
      if (request.path === "/settings") {
        return {
          path: "/settings",
          rows: [{ action: "speech", name: "speech", path: "/settings/speech", meta: "", kind: "dir" }],
        }
      }
      return {
        path: request.path,
        rows: [{ action: "paste", name: "paste", path: `${request.path}/paste`, meta: "on", kind: "pick" }],
      }
    },
  })
  try {
    const app = mount(setup, api)
    await setup.waitForFrame((value) => value.includes("│ /history"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("/speech"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("/paste"))
    setup.mockInput.pressEscape()
    await settle(setup)
    assert.ok(!api.calls.some((call) => call.op === "save"))
    assert.match(setup.captureCharFrame(), /\/settings/)
    setup.mockInput.pressEscape()
    await settle(setup)
    await setup.waitForFrame((value) => value.includes("│ /settings") && value.includes("/digivoice"))
    const saveAt = api.calls.findIndex((call) => call.op === "save")
    assert.ok(saveAt > api.calls.findIndex((call) => call.op === "rows"))
    assert.equal(api.calls.filter((call) => call.op === "save").length, 1)
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("a hotkey is stored only when enter locks it in", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const hotkeyRows = [
    {
      action: "dictation",
      name: "dictation",
      path: "/settings/hotkeys/dictation",
      meta: "Right Option",
      kind: "capture",
    },
    {
      action: "speak",
      name: "speak",
      path: "/settings/hotkeys/speak",
      meta: "Double-tap Left Option",
      kind: "capture",
    },
  ]
  const api = session({
    rows(request) {
      if (request.path === "/settings") {
        return {
          path: "/settings",
          rows: [{ action: "hotkeys", name: "hotkeys", path: "/settings/hotkeys", meta: "", kind: "dir" }],
        }
      }
      return { path: "/settings/hotkeys", rows: hotkeyRows }
    },
    apply(request) {
      return {
        saved: true,
        path: "/settings/hotkeys",
        rows: hotkeyRows.map((row) =>
          row.name === "dictation" ? { ...row, meta: request.text } : row,
        ),
      }
    },
  })
  try {
    const app = mount(setup, api)
    await setup.waitForFrame((value) => value.includes("│ /history"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("/hotkeys"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("/dictation") && value.includes("Right Option"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("input new hotkey"))
    setup.renderer.keyInput.processParsedKey({
      name: "option",
      ctrl: false,
      meta: false,
      shift: false,
      option: true,
      sequence: "",
      number: false,
      raw: "",
      eventType: "press",
      source: "raw",
      keycode: 58,
    })
    await setup.waitForFrame((value) => {
      const line = value.split("\n").find((row) => row.includes("/dictation"))
      return Boolean(line && line.includes("Left Option"))
    })
    setup.mockInput.pressEscape()
    await settle(setup)
    setup.mockInput.pressEnter()
    await setup.renderOnce()
    await setup.waitForFrame((value) => value.includes("input new hotkey"))
    setup.mockInput.pressKey("f")
    await setup.waitForFrame((value) => {
      const line = value.split("\n").find((row) => row.includes("/dictation"))
      return Boolean(line && line.includes("f"))
    })
    assert.ok(!api.calls.some((call) => call.op === "apply"))
    setup.mockInput.pressEscape()
    await settle(setup)
    const cancelled = setup.captureCharFrame()
    assert.match(cancelled, /Right Option/)
    assert.doesNotMatch(cancelled, /input new hotkey/)
    assert.ok(!api.calls.some((call) => call.op === "apply"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("input new hotkey"))
    setup.mockInput.pressKey("f")
    setup.mockInput.pressKey("5")
    await setup.waitForFrame((value) => {
      const line = value.split("\n").find((row) => row.includes("/dictation"))
      return Boolean(line && line.includes("f5"))
    })
    assert.ok(!api.calls.some((call) => call.op === "apply"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("f5") && !value.includes("input new hotkey"))
    const locked = api.calls.filter((call) => call.op === "apply")
    assert.equal(locked.length, 1)
    assert.equal(locked[0].text, "f5")
    const lines = setup.captureCharFrame().split("\n")
    const at = lines.findIndex((line) => line.includes("│ /dictation"))
    assert.ok(at >= 0)
    assert.match(lines[at], /f5/)
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("an unparseable hotkey keeps the previous binding", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const hotkeyRows = [
    {
      action: "dictation",
      name: "dictation",
      path: "/settings/hotkeys/dictation",
      meta: "Right Option",
      kind: "capture",
    },
  ]
  const api = session({
    rows(request) {
      if (request.path === "/settings") {
        return {
          path: "/settings",
          rows: [{ action: "hotkeys", name: "hotkeys", path: "/settings/hotkeys", meta: "", kind: "dir" }],
        }
      }
      return { path: "/settings/hotkeys", rows: hotkeyRows }
    },
    apply() {
      return {
        saved: false,
        note: "dictation binding 'not-a-key' is not a key; keeping Right Option",
        rows: hotkeyRows,
      }
    },
  })
  try {
    const app = mount(setup, api)
    await setup.waitForFrame((value) => value.includes("│ /history"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("/hotkeys"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("/dictation") && value.includes("Right Option"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("input new hotkey"))
    setup.mockInput.pressKey("x")
    await setup.waitForFrame((value) => {
      const line = value.split("\n").find((row) => row.includes("/dictation"))
      return Boolean(line && line.includes("x"))
    })
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("not a key") && value.includes("Right Option"))
    const frame = setup.captureCharFrame()
    assert.match(frame, /│ \/dictation/)
    assert.doesNotMatch(frame, /input new hotkey/)
    const lines = frame.split("\n")
    const at = lines.findIndex((line) => line.includes("│ /dictation"))
    assert.match(lines[at], /Right Option/)
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("reload reset restart and update stay in the page", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session({
    system() {
      return {
        title: "System",
        path: "/system",
        rows: [
          { action: "Reload", path: "/reload", meta: "", kind: "dir", name: "Reload" },
          { action: "Reset", path: "/reset", meta: "", kind: "dir", name: "Reset" },
          { action: "Restart", path: "/restart", meta: "", kind: "dir", name: "Restart" },
          { action: "Update", path: "/update", meta: "", kind: "dir", name: "Update" },
        ],
      }
    },
    update() {
      return { note: "digivoice update\nadapter installed ~/.hammerspoon/digivoice" }
    },
  })
  try {
    const app = mount(setup, api)
    await setup.waitForFrame((value) => value.includes("│ /history"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("│ /reload"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("reloading"))
    await settle(setup)
    await settle(setup)
    await setup.waitForFrame((value) => value.includes("reloaded"))
    assert.match(
      setup.captureCharFrame().split("\n").find((line) => line.includes("ggml-base.en")),
      /ggml-base\.en/,
    )
    setup.mockInput.pressEscape()
    await settle(setup)
    await setup.waitForFrame((value) => value.includes("/reset"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("resetting"))
    await settle(setup)
    await settle(setup)
    await setup.waitForFrame((value) => value.includes("│ /history") && value.includes("/digivoice"))
    assert.ok(api.calls.some((call) => call.op === "reset"))
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("restart paints then re-execs", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session({
    system() {
      return {
        title: "System",
        path: "/system",
        rows: [{ action: "Restart", path: "/restart", meta: "", kind: "dir", name: "Restart" }],
      }
    },
  })
  try {
    const app = mount(setup, api)
    await setup.waitForFrame((value) => value.includes("│ /history"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("│ /restart"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("restarting"))
    await settle(setup)
    await settle(setup)
    assert.equal(await app.done, 0)
    assert.equal(app.restarting, true)
    assert.ok(api.calls.some((call) => call.op === "restart"))
    assert.ok(!api.calls.some((call) => call.op === "quit"))
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("update progress stays off the status line and then restarts", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session({
    system() {
      return {
        title: "System",
        path: "/system",
        rows: [{ action: "Update", path: "/system/update", meta: "", kind: "dir", name: "Update" }],
      }
    },
    update() {
      return { note: "digivoice update\nadapter installed ~/.hammerspoon/digivoice" }
    },
  })
  try {
    const app = mount(setup, api)
    await setup.waitForFrame((value) => value.includes("│ /history"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("│ /update"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("updating"))
    await settle(setup)
    await settle(setup)
    await setup.waitForFrame((value) => value.includes("digivoice update"))
    const lines = setup.captureCharFrame().split("\n")
    const status = lines.find((line) => line.includes("ggml-base.en"))
    assert.match(status, /ggml-base\.en/)
    assert.doesNotMatch(status, /hammerspoon|digivoice update/)
    assert.equal(await app.done, 0)
    assert.equal(app.restarting, true)
    assert.ok(api.calls.some((call) => call.op === "restart"))
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("a failed update stays in the page", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session({
    system() {
      return {
        title: "System",
        path: "/system",
        rows: [{ action: "Update", path: "/system/update", meta: "", kind: "dir", name: "Update" }],
      }
    },
    update() {
      throw new Error("update broke")
    },
  })
  try {
    const app = mount(setup, api)
    await setup.waitForFrame((value) => value.includes("│ /history"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("│ /update"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("updating"))
    await settle(setup)
    await settle(setup)
    await setup.waitForFrame((value) => value.includes("update broke"))
    const lines = setup.captureCharFrame().split("\n")
    const status = lines.find((line) => line.includes("ggml-base.en"))
    assert.match(status, /ggml-base\.en/)
    assert.doesNotMatch(status, /update broke/)
    assert.equal(app.restarting, false)
    assert.ok(!api.calls.some((call) => call.op === "restart"))
    app.destroy()
  } finally {
    setup.renderer.destroy()
  }
})

test("history logs and doctor stay inside the page", async () => {
  const setup = await createTestRenderer({ width: 100, height: 56 })
  const api = session({
    history() {
      return {
        title: "/digivoice/history",
        path: "/history",
        paging: false,
        rows: [
          {
            action: "2026-10-02T12:00:00Z",
            path: "/history",
            text: "ship it",
            meta: "",
            kind: "take",
            index: 0,
          },
        ],
      }
    },
    "history-copy"() {
      return { note: "copied" }
    },
    "history-delete"() {
      return { rows: [], page: 1, pages: 1, paging: false, note: "deleted" }
    },
    doctor() {
      return {
        title: "doctor",
        path: "/doctor",
        ok: true,
        rows: [
          { action: "whisper-cli", path: "", meta: "ok", detail: "Whisper is installed", kind: "check" },
          {
            action: "paths",
            path: "",
            meta: "ok",
            detail: "abcdefghijklmnopqrstuvwxyz".repeat(8),
            kind: "check",
          },
        ],
      }
    },
    logs() {
      return {
        title: "/system/logs",
        path: "/system/logs",
        rows: [
          {
            action: "ready and the rest of this log line",
            text: "ready and the rest of this log line",
            path: "/system/logs",
            meta: "system.log",
            kind: "log",
          },
        ],
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
        rows: [{ action: "speech", path: "/settings/speech", meta: "", kind: "dir", name: "speech" }],
      }
    },
  })
  try {
    const app = mount(setup, api)
    await setup.waitForFrame((value) => value.includes("│ /history"))
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("2026-10-02T12:00:00Z") && value.includes("ship it"))
    let frame = setup.captureCharFrame()
    assert.match(frame, /\/digivoice\/history/)
    const takeLine = frame.split("\n").find((line) => line.includes("2026-10-02T12:00:00Z"))
    assert.ok(takeLine.includes("ship it"))
    assert.doesNotMatch(frame, /Back/)
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("/copy"))
    frame = setup.captureCharFrame()
    assert.match(frame, /ship it/)
    assert.doesNotMatch(frame, /Back/)
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("copied"))
    setup.mockInput.pressKey("d")
    await setup.waitForFrame((value) => value.includes("/digivoice/history") && !value.includes("/copy"))
    assert.doesNotMatch(setup.captureCharFrame(), /Back/)
    setup.mockInput.pressEscape()
    await settle(setup)
    await setup.waitForFrame((value) => value.includes("│ /history"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("/speech"))
    frame = setup.captureCharFrame()
    assert.match(frame, /\/settings/)
    assert.match(frame, /│ \/speech/)
    assert.doesNotMatch(frame, /\/settings\/speech/)
    setup.mockInput.pressEscape()
    await settle(setup)
    await setup.waitForFrame((value) => value.includes("│ /settings") && value.includes("/system"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("│ /doctor"))
    frame = setup.captureCharFrame()
    assert.match(frame, /\/system/)
    assert.match(frame, /│ \/doctor/)
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("whisper-cli"))
    frame = setup.captureCharFrame()
    assert.match(frame, /\bdoctor\b/)
    assert.match(frame, /whisper-cli/)
    assert.match(frame, /Whisper is installed/)
    assert.match(frame, /\bok\b/)
    const longCheck = frame.split("\n").find((line) => line.includes("paths"))
    assert.ok(longCheck.includes("…"))
    assert.ok(longCheck.includes("ok"))
    assert.ok(longCheck.indexOf("…") < longCheck.lastIndexOf("ok"))
    assert.doesNotMatch(frame, /│ whisper-cli/)
    assert.doesNotMatch(frame, /\/doctor/)
    setup.mockInput.pressEscape()
    await settle(setup)
    await setup.waitForFrame((value) => value.includes("/logs"))
    setup.mockInput.pressArrow("down")
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("ready"))
    frame = setup.captureCharFrame()
    assert.match(frame, /\/system\/logs/)
    const logLine = frame.split("\n").find((line) => line.includes("ready"))
    assert.ok(logLine)
    assert.equal((logLine.match(/\n/g) || []).length, 0)
    setup.mockInput.pressEnter()
    await setup.waitForFrame((value) => value.includes("system.log"))
    frame = setup.captureCharFrame()
    assert.match(frame, /ready and the rest of this log line/)
    assert.match(frame, /system\.log/)
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
