import {
  BoxRenderable,
  InputRenderable,
  InputRenderableEvents,
  RGBA,
  ScrollBoxRenderable,
  StyledText,
  TextRenderable,
  createTimeline,
  engine,
  fg,
} from "@opentui/core"

import { BUILD_MS, HERO_GAP, wordmarkLines } from "./hero.js"

export const FOOTER = "↑↓ move · enter select · esc back · click"
export const HOTKEY_PROMPT = "input new hotkey"
export const RULE = "│"

const FRAME_MS = 40
const SPIN = ["·", "··", "···"]
const FRAME_WIDTH = 80
const HERO_FACE = 5
const HERO_SLOT = 6
const FADE_MS = 200

function colorOf(cell) {
  if (!cell.color) return null
  if (cell.color.rgb != null) return RGBA.fromInts(cell.color.rgb, cell.color.rgb, cell.color.rgb)
  return RGBA.fromIndex(cell.color.cube)
}

function paintCells(cells) {
  const chunks = cells.map((cell) => {
    const color = colorOf(cell)
    if (!color) return { __isChunk: true, text: cell.ch }
    return fg(color)(cell.ch)
  })
  return new StyledText(chunks)
}

function mutedColor(truecolor) {
  if (truecolor) return RGBA.fromInts(175, 175, 175)
  return RGBA.fromIndex(145)
}

function mutedLine(text, truecolor) {
  return new StyledText([fg(mutedColor(truecolor))(text)])
}

function statusColor(truecolor, kind) {
  if (kind === "ok") return truecolor ? RGBA.fromInts(80, 180, 90) : RGBA.fromIndex(2)
  return truecolor ? RGBA.fromInts(220, 80, 80) : RGBA.fromIndex(1)
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function oneLine(text) {
  return String(text || "").replace(/\s+/g, " ").trim()
}

function clip(text, width) {
  const value = String(text || "")
  if (value.length <= width) return value
  if (width < 2) return value.slice(0, width)
  return `${value.slice(0, width - 1)}…`
}

function middleEllipsis(text, width) {
  const value = String(text || "")
  if (width < 1) return ""
  if (value.length <= width) return value
  if (width < 2) return "…"
  const keep = width - 1
  const head = Math.ceil(keep / 2)
  const tail = Math.floor(keep / 2)
  return `${value.slice(0, head)}…${value.slice(value.length - tail)}`
}

function barColor(truecolor) {
  if (truecolor) return RGBA.fromInts(36, 36, 40)
  return RGBA.fromIndex(236)
}

function shadowColor(truecolor) {
  if (truecolor) return RGBA.fromInts(68, 68, 68)
  return RGBA.fromIndex(238)
}

function inSettings(path) {
  return String(path || "").startsWith("/settings")
}

function headerFor(screen) {
  if (!screen) return ""
  if (screen.header) return screen.header
  const path = screen.path || "/"
  if (path === "/" || screen.kind === "home") return "/digivoice"
  if (path === "/history" || screen.kind === "history") return "/digivoice/history"
  if (path === "/doctor" || screen.kind === "doctor") return "doctor"
  return path
}

function systemLeaf(row) {
  const path = String(row.path || "")
  if (path === "/system/logs") return "/logs"
  if (path === "/system/update" || path === "/update") return "/update"
  const leaf = path.split("/").filter(Boolean).pop()
  if (leaf) return `/${leaf}`
  return `/${String(row.action || "").toLowerCase()}`
}

function settingsLabel(row) {
  if (row.kind === "choice" && row.meta) return String(row.action || row.name || "")
  const name = String(row.name || row.action || "")
  if (!name) return ""
  return name.startsWith("/") ? name : `/${name}`
}

function rowLabel(row, screen) {
  if (row.kind === "copy") return "/copy"
  if (row.kind === "delete") return "/delete"
  if (row.kind === "confirm" || row.kind === "back") return row.action
  const path = screen.path || "/"
  if (screen.kind === "home" || path === "/") return row.path || `/${String(row.action || "").toLowerCase()}`
  if (screen.kind === "system" || path === "/system") return systemLeaf(row)
  if (inSettings(path)) return settingsLabel(row)
  if (row.kind === "log") return clip(oneLine(row.text || row.action), 72)
  return row.path || row.action
}

function rowValue(row) {
  if (["take", "log", "note", "check", "copy", "delete", "confirm", "back"].includes(row.kind)) {
    return ""
  }
  const meta = String(row.meta || "").trim()
  if (!meta || meta === row.path || meta === row.action) return ""
  if (meta.includes(". ") || meta.endsWith(".")) return ""
  return meta
}

export function optionBinding(key) {
  const name = String(key?.name || "").toLowerCase()
  if (key?.ctrl || key?.shift || key?.super || name.length === 1) return ""
  const named = name === "option" || name === "alt" || name === "opt"
  const modifierOnly = !name && Boolean(key?.option || key?.meta)
  if (!named && !modifierOnly) return ""
  const code = String(key?.code || "")
  const keycode = Number(key?.keycode ?? key?.keyCode)
  const location = key?.location
  if (code === "AltLeft" || location === 1 || location === "left" || keycode === 58) {
    return "Left Option"
  }
  if (code === "AltRight" || location === 2 || location === "right" || keycode === 61) {
    return "Right Option"
  }
  return "Right Option"
}

function chordFrom(key) {
  const option = optionBinding(key)
  if (option) return option
  const name = String(key?.name || "")
  if (!name || name === "escape" || name === "return") return ""
  const modified = Boolean(key.ctrl || key.option || key.meta || key.super)
  if (!modified) return ""
  const parts = []
  if (key.ctrl) parts.push("ctrl")
  if (key.shift) parts.push("shift")
  if (key.option || key.meta) parts.push("alt")
  if (key.super) parts.push("cmd")
  parts.push(name === "space" ? "space" : name)
  return parts.join("+")
}

export function onHangup(session) {
  session.call({ op: "close" })
  return 0
}

export function mountDigivoice(renderer, session, options = {}) {
  const truecolor =
    options.truecolor ??
    ["truecolor", "24bit"].includes(String(process.env.COLORTERM || "").toLowerCase())
  const cols = options.cols ?? 100
  let tMs = options.tMs ?? 0
  const animate = options.animate !== false && options.tMs == null
  let exitCode = 0
  let stopped = false
  let restarting = false
  let working = false
  const stack = []
  let screen = null
  let capture = null
  let hotkeyInput = null
  let hoverIndex = null
  let shownPath = null
  let paneTimeline = null
  let engineAttached = false
  const timelines = []
  let confirmIndex = null
  let finished = false
  let statusText = ""
  let homeRows = []
  let resolveDone = () => {}
  const done = new Promise((resolve) => {
    resolveDone = resolve
  })

  const frameWidth = Math.max(48, Math.min(cols - 2, FRAME_WIDTH))
  const root = new BoxRenderable(renderer, {
    width: "100%",
    height: "100%",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "flex-start",
  })
  const frame = new BoxRenderable(renderer, {
    width: frameWidth,
    height: "100%",
    flexDirection: "column",
    alignItems: "stretch",
  })
  const heroBox = new BoxRenderable(renderer, {
    width: "100%",
    height: HERO_SLOT,
    flexDirection: "column",
    alignItems: "center",
  })
  const shadowBox = new BoxRenderable(renderer, {
    width: "100%",
    height: HERO_SLOT,
    flexDirection: "column",
    alignItems: "center",
  })
  const shadowLines = Array.from(
    { length: HERO_SLOT },
    () => new TextRenderable(renderer, { content: " ", height: 1 }),
  )
  for (const line of shadowLines) shadowBox.add(line)
  const faceBox = new BoxRenderable(renderer, {
    position: "absolute",
    top: 0,
    left: 0,
    width: "100%",
    height: HERO_FACE,
    flexDirection: "column",
    alignItems: "center",
    zIndex: 1,
  })
  const faceLines = Array.from(
    { length: HERO_FACE },
    () => new TextRenderable(renderer, { content: "", height: 1 }),
  )
  for (const line of faceLines) faceBox.add(line)
  heroBox.add(shadowBox)
  heroBox.add(faceBox)
  const statusBox = new BoxRenderable(renderer, { width: "100%", alignItems: "center" })
  const statusNode = new TextRenderable(renderer, { content: "" })
  statusBox.add(statusNode)
  const topGap = new BoxRenderable(renderer, { height: HERO_GAP })
  const page = new BoxRenderable(renderer, {
    flexGrow: 1,
    width: "100%",
    overflow: "hidden",
    flexDirection: "column",
    alignItems: "flex-start",
    justifyContent: "flex-start",
  })
  const column = new BoxRenderable(renderer, {
    width: "100%",
    flexGrow: 1,
    minHeight: 0,
    flexDirection: "column",
    alignItems: "flex-start",
  })
  const list = new BoxRenderable(renderer, {
    width: "100%",
    flexGrow: 1,
    minHeight: 0,
    flexDirection: "column",
    alignItems: "flex-start",
  })
  const historyScroll = new ScrollBoxRenderable(renderer, {
    width: "100%",
    flexGrow: 1,
    flexShrink: 1,
    minHeight: 0,
    stickyScroll: true,
    stickyStart: "bottom",
    scrollX: false,
    viewportCulling: false,
  })
  let historyMounted = false
  const pager = new BoxRenderable(renderer, { flexDirection: "column", alignItems: "flex-start" })
  const bottomGap = new BoxRenderable(renderer, { height: HERO_GAP })
  const footerBox = new BoxRenderable(renderer, { width: "100%", alignItems: "center" })
  const footer = new TextRenderable(renderer, { content: FOOTER })
  footer.onMouseUp = () => {
    goBack()
  }
  footerBox.add(footer)
  column.add(list)
  column.add(pager)
  page.add(column)
  frame.add(heroBox)
  frame.add(statusBox)
  frame.add(topGap)
  frame.add(page)
  frame.add(bottomGap)
  frame.add(footerBox)
  root.add(frame)
  renderer.root.add(root)

  const rowNodes = []
  const pageNodes = []

  function paintShadowLine(cells) {
    const color = shadowColor(truecolor)
    const shifted = [{ ch: " ", color: null }, ...cells]
    const chunks = shifted.map((cell) => {
      if (!cell.ch || cell.ch === " ") return { __isChunk: true, text: cell.ch || " " }
      return fg(color)(cell.ch)
    })
    return new StyledText(chunks)
  }

  function paintHero() {
    const drawn = wordmarkLines("DIGIVOICE", { cols: frameWidth, tMs, truecolor })
    shadowLines[0].content = " "
    drawn.lines.forEach((cells, index) => {
      faceLines[index].content = paintCells(cells)
      shadowLines[index + 1].content = paintShadowLine(cells)
    })
  }

  function fadePane(path) {
    if (path === shownPath) return
    shownPath = path
    if (!animate) {
      page.opacity = 1
      return
    }
    if (paneTimeline) {
      paneTimeline.pause()
      engine.unregister(paneTimeline)
      paneTimeline = null
    }
    page.opacity = 0
    paneTimeline = createTimeline({ duration: FADE_MS })
    paneTimeline.add(page, { opacity: 1, duration: FADE_MS, ease: "outQuad" })
    timelines.push(paneTimeline)
  }

  function clear(box, nodes) {
    for (const node of nodes) box.remove(node)
    nodes.length = 0
  }

  function addLine(box, nodes, content, onPress, textOptions = {}) {
    const node = new TextRenderable(renderer, {
      content,
      height: 1,
      width: textOptions.width,
      truncate: Boolean(textOptions.truncate),
      wrapMode: textOptions.wrapMode,
    })
    if (onPress) node.onMouseUp = onPress
    box.add(node)
    nodes.push(node)
  }

  function detach(node) {
    if (!node.parent) return
    if (node.parent === historyScroll.content) historyScroll.remove(node)
    else node.parent.remove(node)
  }

  function releaseHotkeyField() {
    const field = hotkeyInput
    hotkeyInput = null
    if (field && !field.isDestroyed) field.blur()
  }

  function clearRows() {
    releaseHotkeyField()
    for (const node of rowNodes) detach(node)
    rowNodes.length = 0
  }

  function mountHistory(on) {
    if (on === historyMounted) return
    if (on) list.add(historyScroll)
    else list.remove(historyScroll)
    historyMounted = on
  }

  function paintBars() {
    const bar = barColor(truecolor)
    for (const node of rowNodes) {
      if (node.rowIndex == null) continue
      const active = node.rowIndex === screen.selected || node.rowIndex === hoverIndex
      node.backgroundColor = active ? bar : "transparent"
      if (node.ruleNode) node.ruleNode.content = active ? RULE : " "
    }
  }

  function wrap(text) {
    const width = Math.max(24, cols - 4)
    const raw = String(text || "").replace(/\r/g, "")
    if (!raw.trim()) return []
    const out = []
    for (const paragraph of raw.split("\n")) {
      const words = paragraph.split(/\s+/).filter(Boolean)
      if (!words.length) continue
      let line = ""
      for (const word of words) {
        const next = line ? `${line} ${word}` : word
        if (next.length > width && line) {
          out.push(line)
          line = clip(word, width)
        } else {
          line = next
        }
        if (out.length >= 8) return out
      }
      if (line) out.push(clip(line, width))
      if (out.length >= 8) return out
    }
    return out
  }

  function doctorLine(row) {
    const name = oneLine(row.action)
    const words = oneLine(row.detail || "")
    const status = String(row.meta || "")
    let statusText = status
    let color = null
    if (status === "ok") {
      statusText = "ok"
      color = statusColor(truecolor, "ok")
    } else if (status === "missing") {
      statusText = "not ok"
      color = statusColor(truecolor, "missing")
    }
    const tail = statusText ? `  ${statusText}` : ""
    const head = middleEllipsis(words ? `${name}  ${words}` : name, Math.max(4, frameWidth - tail.length))
    if (!color) return `${head}${tail}`.trimEnd()
    return new StyledText([
      { __isChunk: true, text: `${head}${statusText ? "  " : ""}` },
      fg(color)(statusText),
    ])
  }

  function commitHotkey(value) {
    if (!capture || !screen) return
    const text = String(value || "").trim()
    const index = screen.selected
    const path = screen.path
    capture = null
    releaseHotkeyField()
    if (!text) {
      renderList()
      return
    }
    Promise.resolve(session.call({ op: "apply", path, index, text }))
      .then((result) => {
        screen = {
          ...screen,
          rows: result.rows || screen.rows,
          path: result.path || path,
          selected: index,
          notice: result.saved ? "" : result.note || "",
        }
        renderList()
      })
      .catch(() => renderList())
  }

  function renderRow(row, index) {
    const active = index === screen.selected || index === hoverIndex
    const capturing = Boolean(capture && index === screen.selected && row.kind === "capture")
    const block = new BoxRenderable(renderer, {
      width: "100%",
      height: 1,
      flexDirection: "row",
      alignItems: "center",
      backgroundColor: active ? barColor(truecolor) : "transparent",
    })
    block.rowIndex = index
    const rule = new TextRenderable(renderer, {
      content: active ? RULE : " ",
      width: 1,
      height: 1,
    })
    block.ruleNode = rule
    block.add(rule)
    let label = ""
    let gray = ""
    if (screen.kind === "history" && row.kind === "take") {
      label = String(row.text ? row.action : row.meta || row.action || "")
      gray = oneLine(row.text || (row.meta ? row.action : ""))
    } else if (row.kind === "note") {
      label = String(row.action || "")
    } else {
      label = rowLabel(row, screen)
      if (!capturing) gray = rowValue(row)
    }
    const room = Math.max(4, frameWidth - label.length - 2)
    const action = new TextRenderable(renderer, {
      content: label ? ` ${label}` : "",
      height: 1,
      selectable: row.kind === "take" || row.kind === "log",
      width: row.kind === "log" ? room : undefined,
      truncate: row.kind === "log",
      wrapMode: row.kind === "log" ? "none" : undefined,
    })
    block.add(action)
    if (capturing) {
      const field = new InputRenderable(renderer, {
        placeholder: HOTKEY_PROMPT,
        width: Math.max(HOTKEY_PROMPT.length + 1, room),
        placeholderColor: "#666666",
        textColor: "#FFFFFF",
        focusedTextColor: "#FFFFFF",
      })
      field.on(InputRenderableEvents.ENTER, (value) => {
        commitHotkey(value)
      })
      block.add(field)
      hotkeyInput = field
      queueMicrotask(() => {
        if (hotkeyInput === field && !field.isDestroyed) field.focus()
      })
    } else if (gray) {
      const shown = middleEllipsis(gray, Math.max(1, room - 1))
      block.add(
        new TextRenderable(renderer, {
          content: mutedLine(` ${shown}`, truecolor),
          fg: mutedColor(truecolor),
          width: room,
          height: 1,
          truncate: true,
          wrapMode: "none",
        }),
      )
    }
    if (row.kind !== "note" && row.kind !== "check") {
      block.onMouseOver = () => {
        if (hoverIndex === index) return
        hoverIndex = index
        paintBars()
      }
      block.onMouseOut = () => {
        if (hoverIndex !== index) return
        hoverIndex = null
        paintBars()
      }
      block.onMouseUp = () => {
        if (finished || working || !screen) return
        if (capture && index !== screen.selected) capture = null
        screen.selected = index
        chooseCurrent()
      }
    }
    const parent = screen.kind === "history" && row.kind === "take" ? historyScroll : list
    parent.add(block)
    rowNodes.push(block)
  }

  function renderList() {
    clearRows()
    clear(pager, pageNodes)
    mountHistory(false)
    hoverIndex = null
    statusNode.content = statusText
    if (!screen) {
      paintHero()
      return
    }
    const header = headerFor(screen)
    if (header) addLine(list, rowNodes, header)
    if (screen.kind === "busy") {
      const mark = SPIN[(screen.tick || 0) % SPIN.length]
      addLine(list, rowNodes, `${screen.busyLabel || "working"} ${mark}`)
    } else if (screen.kind === "doctor") {
      for (const row of screen.rows || []) {
        addLine(list, rowNodes, doctorLine(row), null, {
          width: frameWidth,
          truncate: true,
          wrapMode: "none",
        })
      }
    } else {
      for (const line of wrap(screen.body)) addLine(list, rowNodes, line)
      if (screen.notice) addLine(list, rowNodes, screen.notice)
      if (screen.kind === "history") {
        const count = (screen.rows || []).filter((row) => row.kind === "take").length
        const used = HERO_SLOT + 1 + HERO_GAP + HERO_GAP + 2
        const room = Math.max(1, (renderer.height || 24) - used)
        historyScroll.height = Math.max(1, Math.min(Math.max(count, 1), room))
        mountHistory(true)
      }
      ;(screen.rows || []).forEach((row, index) => renderRow(row, index))
    }
    if (screen.paging) {
      addLine(pager, pageNodes, "← previous", () => pageBy(-1))
      addLine(pager, pageNodes, "→ next", () => pageBy(1))
    }
    paintHero()
    fadePane(screen.path || "")
  }

  function finish(code) {
    if (finished) return
    finished = true
    exitCode = code
    if (!stopped) {
      try {
        session.call({ op: "close" })
      } catch {
        /* the banner pid is best-effort */
      }
    }
    resolveDone(code)
  }

  function homeScreen() {
    return {
      path: "/",
      header: "/digivoice",
      rows: homeRows,
      selected: 0,
      kind: "home",
      paging: false,
      body: "",
      notice: "",
      page: 1,
      pages: 1,
    }
  }

  async function persistSettings() {
    capture = null
    await session.call({ op: "save" })
  }

  async function goBack() {
    if (finished || !screen || working) return
    if (capture) {
      capture = null
      renderList()
      return
    }
    if (confirmIndex != null) {
      confirmIndex = null
      const previous = stack.pop()
      if (previous) screen = previous
      renderList()
      return
    }
    const previous = stack.pop()
    const leaving = inSettings(screen.path) && !inSettings(previous && previous.path)
    if (inSettings(screen.path) && (!previous || leaving)) {
      try {
        await persistSettings()
      } catch (error) {
        if (previous) stack.push(previous)
        screen = { ...screen, notice: error && error.message ? error.message : String(error) }
        renderList()
        return
      }
    }
    if (!previous) {
      finish(screen.exitCode != null ? screen.exitCode : 0)
      return
    }
    screen = previous
    renderList()
  }

  async function openBoot() {
    const boot = await session.call({ op: "boot", start: options.start || "/" })
    const opened = boot.screen || {}
    statusText = boot.status || ""
    homeRows = boot.home || opened.rows || []
    const path = opened.path || boot.start || "/"
    const kind =
      path === "/doctor"
        ? "doctor"
        : path === "/history" || String(path).startsWith("/history")
          ? "history"
          : path === "/system/logs"
            ? "logs"
            : path === "/system" || String(path).startsWith("/system")
              ? "system"
              : inSettings(path)
                ? "settings"
                : "home"
    screen = {
      title: opened.title || "Actions",
      path,
      header: headerFor({ path, kind }),
      rows: opened.rows || boot.home || [],
      selected: 0,
      paging: Boolean(opened.paging),
      page: opened.page || 1,
      pages: opened.pages || 1,
      kind,
      body: "",
      notice: "",
      exitCode: opened.ok === false ? 1 : 0,
    }
    renderList()
  }

  async function runBusy(label, header, work) {
    working = true
    const base = {
      ...screen,
      kind: "busy",
      header,
      busyLabel: label,
      tick: 0,
      rows: [],
      body: "",
      notice: "",
      paging: false,
    }
    try {
      screen = base
      renderList()
      await wait(FRAME_MS)
      screen = { ...base, tick: 1 }
      renderList()
      await wait(FRAME_MS)
      return await work()
    } finally {
      working = false
    }
  }

  async function activate() {
    if (!screen || working) return
    const row = (screen.rows || [])[screen.selected]
    if (!row || row.kind === "note" || row.kind === "check" || screen.kind === "doctor") return
    if (row.kind === "back") {
      goBack()
      return
    }
    if (confirmIndex != null && row.kind === "confirm") {
      const saved = await session.call({
        op: "apply",
        path: screen.path,
        index: confirmIndex,
        confirm: true,
      })
      confirmIndex = null
      if (saved.error) {
        screen = { ...screen, notice: saved.error, body: "" }
        renderList()
        return
      }
      if (saved.rows) {
        stack.pop()
        const parent = stack.pop()
        screen = parent
          ? { ...parent, rows: saved.rows, path: saved.path || parent.path, body: "", notice: "" }
          : { ...screen, path: saved.path || screen.path, rows: saved.rows, selected: 0 }
      }
      renderList()
      return
    }
    if (row.kind === "take") {
      stack.push({ ...screen })
      screen = {
        kind: "detail",
        path: "/history",
        header: "/digivoice/history",
        body: row.text || row.action,
        notice: "",
        paging: false,
        page: screen.page,
        rows: [
          { action: "Copy", name: "copy", kind: "copy", index: row.index, path: "/history/copy" },
          {
            action: "Delete",
            name: "delete",
            kind: "delete",
            index: row.index,
            path: "/history/delete",
          },
        ],
        selected: 0,
      }
      renderList()
      return
    }
    if (row.kind === "log") {
      stack.push({ ...screen })
      screen = {
        kind: "detail",
        path: "/system/logs",
        header: "/system/logs",
        body: row.text || row.action,
        notice: row.meta || "",
        rows: [],
        paging: false,
        selected: 0,
      }
      renderList()
      return
    }
    if (row.kind === "copy" || row.kind === "delete") {
      const op = row.kind === "copy" ? "history-copy" : "history-delete"
      const result = await session.call({ op, page: screen.page, index: row.index })
      if (row.kind === "copy") {
        screen = { ...screen, notice: result.note || "copied" }
        renderList()
        return
      }
      if (result.rows) {
        stack.pop()
        screen = {
          header: "/digivoice/history",
          kind: "history",
          path: "/history",
          rows: result.rows,
          page: result.page,
          pages: result.pages,
          paging: result.paging,
          selected: 0,
          body: "",
          notice: "",
        }
      }
      renderList()
      return
    }
    if (row.path === "/quit" || row.action === "Quit") {
      const result = await session.call({ op: "quit" })
      stopped = Boolean(result.stopped)
      finish(0)
      return
    }
    if (row.path === "/history" || row.action === "History") {
      const result = await session.call({ op: "history", page: 1 })
      stack.push({ ...screen })
      screen = {
        ...result,
        path: "/history",
        header: "/digivoice/history",
        selected: 0,
        kind: "history",
        body: "",
        notice: "",
      }
      renderList()
      return
    }
    if (row.path === "/system" || row.action === "System") {
      const result = await session.call({ op: "system" })
      stack.push({ ...screen })
      screen = {
        ...screen,
        ...result,
        path: "/system",
        header: "/system",
        selected: 0,
        kind: "system",
        body: "",
        notice: "",
      }
      renderList()
      return
    }
    if (row.path === "/doctor" || row.action === "Doctor") {
      const result = await session.call({ op: "doctor" })
      stack.push({ ...screen })
      screen = {
        ...screen,
        ...result,
        path: "/doctor",
        header: "doctor",
        selected: 0,
        kind: "doctor",
        body: "",
        notice: "",
        exitCode: result.ok ? 0 : 1,
      }
      renderList()
      return
    }
    if (row.path === "/system/logs" || row.action === "Logs") {
      const result = await session.call({ op: "logs" })
      stack.push({ ...screen })
      screen = {
        ...screen,
        ...result,
        path: "/system/logs",
        header: "/system/logs",
        selected: 0,
        kind: "logs",
        body: "",
        notice: "",
      }
      renderList()
      return
    }
    if (row.path === "/reload" || row.action === "Reload") {
      stack.push({ ...screen })
      await runBusy("reloading", "/reload", () => session.call({ op: "reload" }))
      screen = {
        ...screen,
        kind: "done",
        header: "/reload",
        path: "/reload",
        rows: [],
        body: "reloaded",
        notice: "",
        paging: false,
      }
      renderList()
      return
    }
    if (row.path === "/reset" || row.action === "Reset") {
      await runBusy("resetting", "/reset", () => session.call({ op: "reset" }))
      stack.length = 0
      screen = homeScreen()
      renderList()
      return
    }
    if (row.path === "/restart" || row.action === "Restart") {
      await runBusy("restarting", "/restart", () => session.call({ op: "restart" }))
      restarting = true
      stopped = true
      finish(0)
      return
    }
    if (row.path === "/update" || row.path === "/system/update" || row.action === "Update") {
      stack.push({ ...screen })
      try {
        const result = await runBusy("updating", "/update", () => session.call({ op: "update" }))
        const note = (result && result.note) || ""
        screen = {
          kind: "report",
          header: "/update",
          path: "/system",
          rows: [],
          body: note,
          notice: "",
          selected: 0,
          paging: false,
        }
        renderList()
        if (!/failed/i.test(note)) {
          await wait(FRAME_MS)
          await session.call({ op: "restart" })
          restarting = true
          stopped = true
          finish(0)
        }
      } catch (error) {
        const message = error && error.message ? error.message : String(error)
        screen = {
          kind: "report",
          header: "/update",
          path: "/system",
          rows: [],
          body: message,
          notice: "",
          selected: 0,
          paging: false,
        }
        renderList()
      }
      return
    }
    if (row.path === "/settings" || (row.kind === "dir" && row.action === "Settings")) {
      await openSettings("/settings")
      return
    }
    if (row.kind === "dir" || row.kind === "pick" || String(row.path || "").startsWith("/settings")) {
      const next =
        row.kind === "dir" || row.kind === "pick"
          ? `${screen.path}/${row.name || row.action}`
          : row.path
      await openSettings(next)
    }
  }

  async function openSettings(path) {
    const result = await session.call({ op: "rows", path })
    stack.push({ ...screen })
    const next = result.path || path
    screen = {
      title: String(next).split("/").pop() || "settings",
      path: next,
      header: next,
      rows: result.rows || [],
      selected: 0,
      paging: false,
      kind: "settings",
      body: "",
      notice: "",
      page: 1,
      pages: 1,
    }
    renderList()
  }

  async function chooseCurrent() {
    const row = (screen.rows || [])[screen.selected]
    if (!row) return
    if (row.kind === "capture") {
      capture = {}
      renderList()
      return
    }
    if (row.kind === "choice") {
      const result = await session.call({ op: "apply", path: screen.path, index: screen.selected })
      if (result.confirm) {
        confirmIndex = screen.selected
        stack.push({ ...screen })
        screen = {
          ...screen,
          title: result.title,
          header: screen.header,
          rows: result.rows,
          selected: 0,
          paging: false,
          body: "",
          notice: "",
        }
        renderList()
        return
      }
      if (result.rows) {
        const parent = stack.pop()
        screen = parent
          ? { ...parent, rows: result.rows, path: result.path || parent.path, body: "", notice: "" }
          : { ...screen, rows: result.rows, path: result.path || screen.path }
      }
      renderList()
      return
    }
    await activate()
  }

  function move(delta) {
    if (!screen || working || screen.kind === "doctor" || screen.kind === "busy") return
    if (!screen.rows || !screen.rows.length) return
    const count = screen.rows.length
    screen.selected = (screen.selected + delta + count) % count
    renderList()
  }

  async function pageBy(delta) {
    if (!screen || !screen.paging || working) return
    const pageNo = Math.min(screen.pages, Math.max(1, (screen.page || 1) + delta))
    const result = await session.call({ op: "history", page: pageNo })
    screen = {
      ...screen,
      ...result,
      path: "/history",
      header: "/digivoice/history",
      kind: "history",
      selected: 0,
    }
    renderList()
  }

  function onKey(key) {
    if (finished || working) return
    const name = key.name
    if (capture) {
      if (name === "escape") {
        if (typeof key.stopPropagation === "function") key.stopPropagation()
        capture = null
        renderList()
        return
      }
      const chord = chordFrom(key)
      if (chord && hotkeyInput) {
        if (typeof key.stopPropagation === "function") key.stopPropagation()
        hotkeyInput.value = chord
      }
      return
    }
    if (name === "up") move(-1)
    else if (name === "down") move(1)
    else     if (name === "return") chooseCurrent()
    else if (name === "escape") goBack()
    else if (name === "left" && screen && screen.paging) pageBy(-1)
    else if (name === "right" && screen && screen.paging) pageBy(1)
    else if ((name === "c" || name === "d") && screen) {
      const kind = name === "c" ? "copy" : "delete"
      const index = (screen.rows || []).findIndex((row) => row.kind === kind)
      if (index >= 0) {
        screen.selected = index
        activate()
      }
    }
  }

  const keyInput = renderer.keyInput
  const processParsedKey = keyInput.processParsedKey.bind(keyInput)
  keyInput.processParsedKey = (parsed) => {
    if (parsed && parsed.code == null) {
      const keycode = Number(parsed.keycode ?? parsed.keyCode)
      if (keycode === 58) parsed.code = "AltLeft"
      else if (keycode === 61) parsed.code = "AltRight"
    }
    return processParsedKey(parsed)
  }
  keyInput.on("keypress", onKey)
  paintHero()
  if (animate) {
    engine.attach(renderer)
    engineAttached = true
    shadowBox.opacity = 1
    const shadowTimeline = createTimeline({ loop: true, duration: 2800 })
    shadowTimeline.add(shadowBox, {
      opacity: 0.2,
      duration: 1400,
      ease: "linear",
      alternate: true,
      loop: true,
    })
    timelines.push(shadowTimeline)
  }
  const timer = animate
    ? setInterval(() => {
        tMs += 80
        paintHero()
        if (tMs >= BUILD_MS + 1800) tMs = BUILD_MS
      }, 80)
    : null

  openBoot().catch((error) => {
    screen = {
      title: "digivoice",
      path: "/",
      header: "/digivoice",
      kind: "home",
      rows: [{ action: String(error.message || error), path: "/", meta: "", kind: "note" }],
      selected: 0,
      body: "",
      notice: "",
    }
    renderList()
  })

  return {
    done,
    get exitCode() {
      return exitCode
    },
    get restarting() {
      return restarting
    },
    destroy() {
      if (timer) clearInterval(timer)
      keyInput.processParsedKey = processParsedKey
      keyInput.off("keypress", onKey)
      if (paneTimeline) {
        paneTimeline.pause()
        engine.unregister(paneTimeline)
      }
      for (const timeline of timelines) engine.unregister(timeline)
      if (engineAttached) engine.detach()
    },
  }
}
