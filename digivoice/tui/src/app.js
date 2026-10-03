import {
  BoxRenderable,
  InputRenderable,
  InputRenderableEvents,
  RGBA,
  ScrollBoxRenderable,
  StyledText,
  TextRenderable,
  bg,
  createTimeline,
  engine,
  fg,
} from "@opentui/core"

import { HERO_GAP, pixelScale, slotRowsFor, wordmarkLines } from "./hero.js"
import { menuPaint } from "./menu_colors.js"

export const FOOTER = "↑↓ move · enter select · esc back · click"
export const HOTKEY_PROMPT = "input new hotkey"
export const RULE = "│"

const FRAME_MS = 40
const SPIN = ["·", "··", "···"]
const FRAME_WIDTH = 80
const HERO_FACE = 5
const HERO_SLOT = 6
const MAX_SLOT = slotRowsFor(3)
const FADE_MS = 200
const STATUS_ROWS = 1
const FOOTER_ROWS = 1
const MIN_MENU_ROWS = 3
const STATUS_MARK = "─"

export function heroOffset(rows, slot = HERO_SLOT) {
  const height = Math.max(0, Math.floor(Number(rows) || 0))
  const chrome = slot + HERO_GAP + STATUS_ROWS + MIN_MENU_ROWS + FOOTER_ROWS + HERO_GAP
  const room = height - chrome
  if (room <= 0) return 0
  return Math.min(Math.floor(height / 3), room)
}

export function statusParts(text) {
  const raw = oneLine(text)
  const pieces = raw.split(" · ").filter(Boolean)
  const summary = pieces.length ? pieces[pieces.length - 1] : ""
  const head = pieces.length > 1 ? pieces.slice(0, -1).join(" · ") : ""
  return { mark: STATUS_MARK, head, summary, kind: summaryKind(summary) }
}

function summaryKind(summary) {
  const value = summary.trim().toLowerCase()
  if (!value) return "info"
  if (value.startsWith("ok")) return "ok"
  if (value.startsWith("not ") || value.includes("missing") || value.includes("unavailable")) return "missing"
  return "info"
}

let activeTheme = null

function rgbaFromChannels(channels) {
  if (!channels) return null
  if (channels.cube != null) return RGBA.fromIndex(channels.cube)
  return RGBA.fromInts(channels[0], channels[1], channels[2])
}

function statusLine(text, truecolor) {
  const parts = statusParts(text)
  const paint = menuPaint(activeTheme, truecolor)
  const ink = rgbaFromChannels(paint.statusText)
  const plain = (value) =>
    value && ink ? fg(ink)(value) : { __isChunk: true, text: value }
  const chunks = [fg(ink || mutedColor(truecolor))(`${parts.mark} `)]
  if (parts.head) chunks.push(plain(`${parts.head} · `))
  if (!parts.summary || parts.kind === "info") chunks.push(plain(parts.summary))
  else {
    const status = rgbaFromChannels(paint.status) || statusColor(truecolor, parts.kind)
    chunks.push(fg(status)(parts.summary))
  }
  return new StyledText(chunks)
}

function rgbaOf(color) {
  if (!color) return null
  if (Array.isArray(color.rgb)) return RGBA.fromInts(color.rgb[0], color.rgb[1], color.rgb[2])
  if (color.rgb != null) return RGBA.fromInts(color.rgb, color.rgb, color.rgb)
  return RGBA.fromIndex(color.cube)
}

function hexChannels(hex) {
  if (!hex || typeof hex !== "string") return null
  let body = hex.replace("#", "")
  if (body.length === 3) body = body.split("").map((ch) => ch + ch).join("")
  if (body.length !== 6) return null
  const value = Number.parseInt(body, 16)
  if (Number.isNaN(value)) return null
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255]
}

function paintCells(cells) {
  const chunks = cells.map((cell) => {
    const front = rgbaOf(cell.color)
    const back = rgbaOf(cell.bg)
    if (!front && !back) return { __isChunk: true, text: cell.ch }
    let chunk = cell.ch
    if (front) chunk = fg(front)(chunk)
    if (back) chunk = bg(back)(chunk)
    return chunk
  })
  return new StyledText(chunks)
}

function mutedColor(truecolor, theme = activeTheme) {
  return rgbaFromChannels(menuPaint(theme, truecolor).value)
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

function barColor(truecolor, theme = activeTheme) {
  if (theme && theme.active && truecolor) {
    const rgb = hexChannels(theme.accent)
    if (rgb) return RGBA.fromInts(rgb[0], rgb[1], rgb[2])
  }
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

function chosenIndex(rows, selected) {
  const count = Array.isArray(rows) ? rows.length : 0
  if (!count || !Number.isInteger(selected)) return 0
  if (selected < 0) return 0
  if (selected >= count) return count - 1
  return selected
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

function barLine(percent) {
  const width = 24
  const pct = Math.max(0, Math.min(100, Number(percent) || 0))
  const filled = Math.round((width * pct) / 100)
  return `${"█".repeat(filled)}${"░".repeat(width - filled)}  ${pct}%`
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
  function takeTheme(result) {
    if (result && result.theme) activeTheme = result.theme.active ? result.theme : null
  }
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
  let downloadJob = null
  let downloadGen = 0
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
    flexShrink: 0,
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
    { length: MAX_SLOT },
    (_, index) => new TextRenderable(renderer, { content: " ", height: index < HERO_SLOT ? 1 : 0 }),
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
    { length: MAX_SLOT - 1 },
    (_, index) => new TextRenderable(renderer, { content: "", height: index < HERO_FACE ? 1 : 0 }),
  )
  for (const line of faceLines) faceBox.add(line)
  heroBox.add(shadowBox)
  heroBox.add(faceBox)
  const lift = new BoxRenderable(renderer, {
    width: "100%",
    height: heroOffset(renderer.height || 0),
    flexShrink: 0,
  })
  const wordGap = new BoxRenderable(renderer, { height: HERO_GAP, flexShrink: 0 })
  const statusBox = new BoxRenderable(renderer, {
    width: "100%",
    height: STATUS_ROWS,
    flexShrink: 0,
    alignItems: "flex-start",
  })
  const statusNode = new TextRenderable(renderer, {
    content: "",
    height: 1,
    width: frameWidth,
    truncate: true,
    wrapMode: "none",
  })
  statusBox.add(statusNode)
  const page = new ScrollBoxRenderable(renderer, {
    width: "100%",
    flexGrow: 1,
    flexShrink: 1,
    minHeight: 0,
    stickyScroll: false,
    scrollX: false,
    viewportCulling: false,
    contentOptions: { minHeight: 0 },
  })
  const column = new BoxRenderable(renderer, {
    width: "100%",
    flexDirection: "column",
    alignItems: "flex-start",
  })
  const list = new BoxRenderable(renderer, {
    width: "100%",
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
  const bottomGap = new BoxRenderable(renderer, { height: HERO_GAP, flexShrink: 0 })
  const footerBox = new BoxRenderable(renderer, { width: "100%", flexShrink: 0, alignItems: "center" })
  const footer = new TextRenderable(renderer, { content: FOOTER })
  footer.onMouseUp = () => {
    goBack()
  }
  footerBox.add(footer)
  column.add(list)
  column.add(pager)
  page.add(column)
  frame.add(lift)
  frame.add(heroBox)
  frame.add(wordGap)
  frame.add(statusBox)
  frame.add(page)
  frame.add(bottomGap)
  frame.add(footerBox)
  root.add(frame)
  renderer.root.add(root)

  const rowNodes = []
  const pageNodes = []

  let heroSlot = HERO_SLOT

  function paintShadowLine(cells) {
    const color = shadowColor(truecolor)
    const shifted = [{ ch: " ", color: null }, ...cells]
    const chunks = shifted.map((cell) => {
      if (!cell.ch || cell.ch === " ") return { __isChunk: true, text: cell.ch || " " }
      const mark = fg(color)(cell.ch)
      return cell.bg ? bg(color)(mark) : mark
    })
    return new StyledText(chunks)
  }

  function paintHero() {
    const termW = Math.max(1, renderer.width || frameWidth)
    const termH = Math.max(0, renderer.height || 0)
    const scale = pixelScale({ cols: termW, rows: termH, letters: 9 })
    const drawCols = scale === 1 ? frameWidth : termW
    const ink = activeTheme && activeTheme.active ? hexChannels(activeTheme.accent) : null
    const drawn = wordmarkLines("DIGIVOICE", { cols: drawCols, rows: termH, tMs, truecolor, scale, ink })
    const markWidth = drawn.lines[0]?.length ?? 0
    const nextFrame = Math.max(frameWidth, Math.min(termW, markWidth + 2))
    if (frame.width !== nextFrame) frame.width = nextFrame
    const faceRows = drawn.rows
    heroSlot = faceRows + 1
    heroBox.height = heroSlot
    shadowBox.height = heroSlot
    faceBox.height = faceRows
    shadowLines.forEach((line, index) => {
      line.height = index < heroSlot ? 1 : 0
      if (index >= heroSlot) line.content = " "
    })
    faceLines.forEach((line, index) => {
      line.height = index < faceRows ? 1 : 0
      if (index >= faceRows) line.content = ""
    })
    lift.height = heroOffset(termH, heroSlot)
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

  function armCapture(active) {
    try {
      session.call({ op: "hotkey-capture", active: Boolean(active) })
    } catch {
      /* the field still opens when the flag cannot be written */
    }
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
    armCapture(false)
    if (!text) {
      renderList()
      return
    }
    Promise.resolve(session.call({ op: "apply", path, index, text }))
      .then((result) => {
        takeTheme(result)
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
    const mark = row.downloaded ? 1 : 0
    const room = Math.max(4, frameWidth - label.length - 2 - mark)
    const rowColor = rgbaFromChannels(menuPaint(activeTheme, truecolor).row)
    const action = new TextRenderable(renderer, {
      content: label ? ` ${label}` : "",
      height: 1,
      selectable: row.kind === "take" || row.kind === "log",
      width: row.kind === "log" ? room : undefined,
      truncate: row.kind === "log",
      wrapMode: row.kind === "log" ? "none" : undefined,
      ...(rowColor ? { fg: rowColor } : {}),
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
    if (row.downloaded) {
      block.add(new BoxRenderable(renderer, { flexGrow: 1, height: 1 }))
      block.add(new TextRenderable(renderer, { content: "↓", width: 1, height: 1 }))
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
        if (capture && index !== screen.selected) {
          capture = null
          armCapture(false)
        }
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
    statusNode.content = statusLine(statusText, truecolor)
    if (!screen) {
      paintHero()
      return
    }
    const header = headerFor(screen)
    if (header) addLine(list, rowNodes, header)
    if (screen.kind === "busy") {
      const mark = SPIN[(screen.tick || 0) % SPIN.length]
      addLine(list, rowNodes, `${screen.busyLabel || "working"} ${mark}`)
    } else if (screen.kind === "download") {
      addLine(list, rowNodes, screen.downloadName || "")
      addLine(list, rowNodes, barLine(screen.percent || 0))
      if (screen.downloadError) addLine(list, rowNodes, screen.downloadError)
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
        const used =
          heroOffset(renderer.height || 24, heroSlot) +
          heroSlot +
          HERO_GAP +
          STATUS_ROWS +
          HERO_GAP +
          FOOTER_ROWS
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
    pinSelection()
    fadePane(screen.path || "")
  }

  function pinSelection() {
    if (!screen || !["home", "settings", "system", "logs"].includes(screen.kind)) return
    const target = (headerFor(screen) ? 1 : 0) + (screen.selected || 0)
    const view = page.viewport ? page.viewport.height : 0
    if (view <= 0) return
    const top = page.scrollTop || 0
    if (target < top) page.scrollTop = target
    else if (target >= top + view) page.scrollTop = target - view + 1
  }

  function scrollMenu(rows) {
    page.scrollTop = Math.max(0, (page.scrollTop || 0) + rows)
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
    armCapture(false)
    await session.call({ op: "save" })
  }

  async function goBack() {
    if (finished || !screen || working) return
    if (capture) {
      capture = null
      armCapture(false)
      renderList()
      return
    }
    if (screen.kind === "download") {
      downloadGen += 1
      if (downloadJob) downloadJob.cancel()
      downloadJob = null
      try {
        session.call({ op: "cancel-download", filename: screen.filename || "" })
      } catch {
        /* leaving the page still drops the partial on the next open */
      }
      const previous = stack.pop()
      if (previous) screen = previous
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
    takeTheme(boot)
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
      selected: chosenIndex(opened.rows || boot.home || [], opened.selected),
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
      takeTheme(saved)
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
      const result = await runBusy("reloading", "/reload", () => session.call({ op: "reload" }))
      const note = String((result && result.note) || "").trim()
      screen = {
        ...screen,
        kind: "done",
        header: "/reload",
        path: "/reload",
        rows: [],
        body: note || (result && result.ok === false ? "reload failed" : "reloaded"),
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
        const failed =
          result && typeof result.ok === "boolean" ? result.ok === false : /failed/i.test(note)
        if (!failed) {
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
      selected: chosenIndex(result.rows || [], result.selected),
      paging: false,
      kind: "settings",
      body: "",
      notice: "",
      page: 1,
      pages: 1,
    }
    renderList()
  }

  function beginDownload(result) {
    const gen = ++downloadGen
    const listIndex = screen.selected
    const listPath = screen.path
    stack.push({ ...screen })
    screen = {
      ...screen,
      kind: "download",
      downloadName: result.name || result.title || result.filename,
      filename: result.filename,
      percent: 0,
      downloadError: "",
      rows: [],
      body: "",
      notice: "",
      paging: false,
      listIndex,
    }
    renderList()
    const follow = session.follow
    if (typeof follow !== "function") {
      screen = { ...screen, downloadError: "download is unavailable" }
      renderList()
      return
    }
    downloadJob = follow(
      { op: "download", path: result.path || listPath, index: result.index ?? listIndex, filename: result.filename },
      (event) => {
        if (gen !== downloadGen || !screen || screen.kind !== "download") return
        if (event.error) {
          screen = { ...screen, downloadError: String(event.error) }
          renderList()
          return
        }
        if (event.got != null) {
          const total = Number(event.total)
          const percent = total > 0 ? Math.min(100, Math.round((Number(event.got) * 100) / total)) : screen.percent
          screen = { ...screen, percent }
          renderList()
        }
        if (event.ok) {
          downloadJob = null
          const previous = stack.pop()
          screen = {
            ...(previous || screen),
            kind: "settings",
            path: event.path || listPath,
            rows: event.rows || (previous && previous.rows) || [],
            selected: event.index ?? listIndex,
            body: "",
            notice: "",
            downloadError: "",
          }
          renderList()
        }
      },
    )
  }

  async function chooseCurrent() {
    const row = (screen.rows || [])[screen.selected]
    if (!row || (screen && screen.kind === "download")) return
    if (row.kind === "capture") {
      capture = {}
      armCapture(true)
      renderList()
      return
    }
    if (row.kind === "choice") {
      const result = await session.call({ op: "apply", path: screen.path, index: screen.selected })
      takeTheme(result)
      if (result.download) {
        beginDownload(result)
        return
      }
      if (result.stay) {
        screen = {
          ...screen,
          rows: result.rows || screen.rows,
          path: result.path || screen.path,
          selected: result.index ?? screen.selected,
          body: "",
          notice: "",
        }
        renderList()
        return
      }
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
    if (!screen || working || screen.kind === "doctor" || screen.kind === "busy" || screen.kind === "download") return
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
    if (screen && screen.kind === "download" && name !== "escape") return
    if (capture) {
      if (name === "escape") {
        if (typeof key.stopPropagation === "function") key.stopPropagation()
        capture = null
        armCapture(false)
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
  shadowBox.opacity = 1
  paintHero()
  if (animate) {
    engine.attach(renderer)
    engineAttached = true
  }
  const timer = animate
    ? setInterval(() => {
        tMs += 80
        paintHero()
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
    scrollMenu,
    destroy() {
      armCapture(false)
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
