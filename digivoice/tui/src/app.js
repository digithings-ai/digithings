import { BoxRenderable, RGBA, StyledText, TextRenderable, fg } from "@opentui/core"

import { BUILD_MS, HERO_GAP, wordmarkLines } from "./hero.js"

export const FOOTER = "↑↓ move · enter select · esc back · click"
export const HOTKEY_PROMPT = "input new hotkey"

const FRAME_MS = 40
const SPIN = ["·", "··", "···"]
const FRAME_WIDTH = 80

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

function mixedLine(head, tail, truecolor) {
  if (!tail) return head
  return new StyledText([{ __isChunk: true, text: head }, fg(mutedColor(truecolor))(tail)])
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
  if (meta.length > 48) return ""
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

function draftFrom(key) {
  const name = key.name
  const option = optionBinding(key)
  if (name === "backspace") return { edit: "backspace" }
  if (option) return { replace: option }
  const modified = Boolean(key.ctrl || key.option || key.meta || key.super)
  if (modified) {
    const parts = []
    if (key.ctrl) parts.push("ctrl")
    if (key.shift) parts.push("shift")
    if (key.option || key.meta) parts.push("alt")
    if (key.super) parts.push("cmd")
    parts.push(name === "space" ? "space" : name)
    return { replace: parts.join("+") }
  }
  if (name === "space") return { append: " " }
  if (name && name.length === 1) return { append: name }
  return { replace: name || "" }
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
    flexDirection: "column",
    alignItems: "center",
  })
  const heroLines = Array.from({ length: 5 }, () => new TextRenderable(renderer, { content: "" }))
  for (const line of heroLines) heroBox.add(line)
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
    flexDirection: "column",
    alignItems: "flex-start",
  })
  const list = new BoxRenderable(renderer, {
    width: "100%",
    flexDirection: "column",
    alignItems: "flex-start",
  })
  const pager = new BoxRenderable(renderer, { flexDirection: "column", alignItems: "flex-start" })
  const bottomGap = new BoxRenderable(renderer, { height: HERO_GAP })
  const footerBox = new BoxRenderable(renderer, { width: "100%", alignItems: "center" })
  const footer = new TextRenderable(renderer, { content: FOOTER })
  footer.onMouseDown = () => {
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

  function paintHero() {
    const drawn = wordmarkLines("DIGIVOICE", { cols: frameWidth, tMs, truecolor })
    drawn.lines.forEach((cells, index) => {
      heroLines[index].content = paintCells(cells)
    })
  }

  function clear(box, nodes) {
    for (const node of nodes) box.remove(node)
    nodes.length = 0
  }

  function addLine(box, nodes, content, onPress) {
    const node = new TextRenderable(renderer, { content })
    if (onPress) node.onMouseDown = onPress
    box.add(node)
    nodes.push(node)
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
    const name = clip(oneLine(row.action), 18)
    const words = clip(oneLine(row.detail || ""), 40)
    const status = String(row.meta || "")
    const head = words ? `${name}  ${words}  ` : `${name}  `
    if (status === "ok") {
      return new StyledText([
        { __isChunk: true, text: head },
        fg(statusColor(truecolor, "ok"))(status),
      ])
    }
    if (status === "missing") {
      return new StyledText([
        { __isChunk: true, text: head },
        fg(statusColor(truecolor, "missing"))("not ok"),
      ])
    }
    return `${head}${status}`.trimEnd()
  }

  function historyLine(row, selected) {
    const when = row.text ? row.action : row.meta || row.action
    const text = clip(oneLine(row.text || (row.meta ? row.action : "")), 52)
    const head = `${selected ? "[*]" : "[ ]"} ${when}`
    if (!text) return head
    return mixedLine(`${head}  `, text, truecolor)
  }

  function renderRow(row, index) {
    const selected = index === screen.selected
    const press = () => {
      if (capture && index !== screen.selected) capture = null
      screen.selected = index
      chooseCurrent()
    }
    const block = new BoxRenderable(renderer, {
      flexDirection: "column",
      alignItems: "flex-start",
    })
    let content
    if (screen.kind === "history" && row.kind === "take") content = historyLine(row, selected)
    else if (row.kind === "note") content = row.action
    else content = `${selected ? "[*]" : "[ ]"} ${rowLabel(row, screen)}`
    const action = new TextRenderable(renderer, { content })
    if (row.kind !== "note") action.onMouseDown = press
    block.add(action)
    let gray = ""
    if (capture && selected && row.kind === "capture") {
      gray = capture.text ? `${HOTKEY_PROMPT}  ${capture.text}` : HOTKEY_PROMPT
    } else if (row.kind !== "note" && screen.kind !== "history") {
      gray = rowValue(row)
    }
    if (gray) {
      const line = new TextRenderable(renderer, {
        content: mutedLine(gray, truecolor),
      })
      if (row.kind !== "note") line.onMouseDown = press
      block.add(line)
    }
    list.add(block)
    rowNodes.push(block)
  }

  function renderList() {
    clear(list, rowNodes)
    clear(pager, pageNodes)
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
      for (const row of screen.rows || []) addLine(list, rowNodes, doctorLine(row))
    } else {
      for (const line of wrap(screen.body)) addLine(list, rowNodes, line)
      if (screen.notice) addLine(list, rowNodes, screen.notice)
      ;(screen.rows || []).forEach((row, index) => renderRow(row, index))
    }
    if (screen.paging) {
      addLine(pager, pageNodes, "← previous", () => pageBy(-1))
      addLine(pager, pageNodes, "→ next", () => pageBy(1))
    }
    paintHero()
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
      capture = { text: "" }
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
        capture = null
        renderList()
        return
      }
      if (name === "return") {
        const text = capture.text.trim()
        const index = screen.selected
        const path = screen.path
        capture = null
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
        return
      }
      const draft = draftFrom(key)
      if (draft.edit === "backspace") capture.text = capture.text.slice(0, -1)
      else if (draft.append != null) capture.text += draft.append
      else if (draft.replace) capture.text = draft.replace
      renderList()
      return
    }
    if (name === "up") move(-1)
    else if (name === "down") move(1)
    else if (name === "return") chooseCurrent()
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

  renderer.keyInput.on("keypress", onKey)
  paintHero()
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
      renderer.keyInput.off("keypress", onKey)
    },
  }
}
