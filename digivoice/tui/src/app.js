import { BoxRenderable, RGBA, StyledText, TextRenderable, fg } from "@opentui/core"

import { BUILD_MS, HERO_GAP, wordmarkLines } from "./hero.js"

export const FOOTER = "↑↓ move · enter select · esc back · click"

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

function rowLabel(row, selected) {
  const mark = selected ? "[*]" : "[ ]"
  const meta = row.meta ? `  ${row.meta}` : ""
  return `${mark} ${row.action}${meta}`
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
  const stack = []
  let screen = null
  let capture = null
  let confirmIndex = null
  let finished = false
  let resolveDone = () => {}
  const done = new Promise((resolve) => {
    resolveDone = resolve
  })

  const root = new BoxRenderable(renderer, {
    width: "100%",
    height: "100%",
    flexDirection: "column",
    alignItems: "center",
  })
  const heroBox = new BoxRenderable(renderer, { flexDirection: "column", alignItems: "center" })
  const heroLines = Array.from({ length: 5 }, () => new TextRenderable(renderer, { content: "" }))
  for (const line of heroLines) heroBox.add(line)
  const gap = new BoxRenderable(renderer, { height: HERO_GAP })
  const contextBox = new BoxRenderable(renderer, { flexDirection: "column", alignItems: "center" })
  const list = new BoxRenderable(renderer, { flexDirection: "column", alignItems: "flex-start" })
  const pager = new BoxRenderable(renderer, { flexDirection: "column", alignItems: "flex-start" })
  const footer = new TextRenderable(renderer, { content: FOOTER })
  footer.onMouseDown = () => {
    goBack()
  }
  root.add(heroBox)
  root.add(gap)
  root.add(contextBox)
  root.add(list)
  root.add(pager)
  root.add(footer)
  renderer.root.add(root)

  const rowNodes = []
  const pageNodes = []
  const contextNodes = []

  function paintHero() {
    const frame = wordmarkLines("DIGIVOICE", { cols, tMs, truecolor })
    frame.lines.forEach((cells, index) => {
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

  function renderList() {
    clear(list, rowNodes)
    clear(pager, pageNodes)
    clear(contextBox, contextNodes)
    if (!screen) return
    for (const line of screen.context || []) {
      addLine(contextBox, contextNodes, line)
    }
    const rows = screen.rows || []
    rows.forEach((row, index) => {
      addLine(list, rowNodes, rowLabel(row, index === screen.selected), () => {
        screen.selected = index
        chooseCurrent()
      })
    })
    if (screen.paging) {
      addLine(pager, pageNodes, "← previous", () => pageBy(-1))
      addLine(pager, pageNodes, "→ next", () => pageBy(1))
    }
    if (capture) addLine(pager, pageNodes, `key: ${capture.text || ""}`)
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

  function goBack() {
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
    if (!previous) {
      finish(screen && screen.exitCode != null ? screen.exitCode : 0)
      return
    }
    screen = previous
    renderList()
  }

  async function openBoot() {
    const boot = await session.call({ op: "boot", start: options.start || "/" })
    const opened = boot.screen || {}
    screen = {
      title: opened.title || "Actions",
      path: opened.path || boot.start || "/",
      rows: opened.rows || boot.home || [],
      selected: 0,
      paging: Boolean(opened.paging),
      page: opened.page || 1,
      pages: opened.pages || 1,
      context: boot.context || [],
      kind: opened.path === "/doctor" ? "doctor" : "list",
      exitCode: opened.ok === false ? 1 : 0,
    }
    renderList()
  }

  async function activate() {
    if (!screen) return
    const row = (screen.rows || [])[screen.selected]
    if (!row) return
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
        screen = { ...screen, context: [saved.error] }
        renderList()
        return
      }
      if (saved.rows) {
        stack.pop()
        const parent = stack.pop()
        screen = parent
          ? { ...parent, rows: saved.rows, path: saved.path || parent.path }
          : { ...screen, path: saved.path || screen.path, rows: saved.rows, selected: 0 }
      }
      renderList()
      return
    }
    if (row.kind === "take") {
      stack.push({ ...screen })
      screen = {
        ...screen,
        title: "Take",
        path: "/history",
        paging: false,
        context: [row.action, row.meta].filter(Boolean),
        rows: [
          { action: "Copy", path: "/history/copy", meta: "c", kind: "copy", index: row.index },
          { action: "Delete", path: "/history/delete", meta: "d", kind: "delete", index: row.index },
          { action: "Back", path: "/history", meta: "", kind: "back" },
        ],
        selected: 0,
      }
      renderList()
      return
    }
    if (row.kind === "copy" || row.kind === "delete") {
      const op = row.kind === "copy" ? "history-copy" : "history-delete"
      const result = await session.call({ op, page: screen.page, index: row.index })
      if (row.kind === "delete" && result.rows) {
        stack.pop()
        screen = {
          ...screen,
          rows: result.rows,
          page: result.page,
          pages: result.pages,
          paging: result.paging,
          selected: 0,
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
      screen = { ...result, selected: 0, context: screen.context, kind: "history" }
      renderList()
      return
    }
    if (row.path === "/system" || row.action === "System") {
      const result = await session.call({ op: "system" })
      stack.push({ ...screen })
      screen = { ...screen, ...result, selected: 0, kind: "system" }
      renderList()
      return
    }
    if (row.path === "/doctor" || row.action === "Doctor") {
      const result = await session.call({ op: "doctor" })
      stack.push({ ...screen })
      screen = { ...screen, ...result, selected: 0, kind: "doctor", exitCode: result.ok ? 0 : 1 }
      renderList()
      return
    }
    if (row.path === "/system/logs" || row.action === "Logs") {
      const result = await session.call({ op: "logs" })
      stack.push({ ...screen })
      screen = { ...screen, ...result, selected: 0, kind: "logs" }
      renderList()
      return
    }
    if (row.path === "/reload" || row.action === "Reload") {
      await session.call({ op: "reload" })
      renderList()
      return
    }
    if (row.path === "/reset" || row.action === "Reset") {
      stack.push({ ...screen })
      screen = {
        ...screen,
        title: "Reset",
        path: "/reset",
        rows: [
          { action: "Reset", path: "/reset", meta: "", kind: "reset-confirm" },
          { action: "Back", path: "/system", meta: "", kind: "back" },
        ],
        selected: 0,
        paging: false,
      }
      renderList()
      return
    }
    if (row.kind === "reset-confirm") {
      await session.call({ op: "reset" })
      goBack()
      return
    }
    if (row.kind === "restart-confirm") {
      await session.call({ op: "restart" })
      restarting = true
      stopped = true
      finish(0)
      return
    }
    if (row.path === "/restart" || row.action === "Restart") {
      stack.push({ ...screen })
      screen = {
        ...screen,
        title: "Restart",
        path: "/restart",
        rows: [
          { action: "Restart", path: "/restart", meta: "", kind: "restart-confirm" },
          { action: "Back", path: "/system", meta: "", kind: "back" },
        ],
        selected: 0,
        paging: false,
      }
      renderList()
      return
    }
    if (row.path === "/update" || row.action === "Update") {
      const result = await session.call({ op: "update" })
      screen = { ...screen, context: result.note ? [result.note] : [] }
      renderList()
      return
    }
    if (row.path === "/settings" || (row.kind === "dir" && row.action === "Settings")) {
      await openSettings("/settings")
      return
    }
    if (row.kind === "dir" || row.kind === "pick" || String(row.path || "").startsWith("/settings")) {
      await openSettings(row.kind === "dir" || row.kind === "pick" ? `${screen.path}/${row.name || row.action}` : row.path)
      return
    }
  }

  async function openSettings(path) {
    const result = await session.call({ op: "rows", path })
    stack.push({ ...screen })
    screen = {
      ...screen,
      title: String(path).split("/").pop() || "settings",
      path: result.path || path,
      rows: result.rows || [],
      selected: 0,
      paging: false,
      kind: "settings",
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
        screen = { ...screen, title: result.title, rows: result.rows, selected: 0, paging: false }
        renderList()
        return
      }
      if (result.rows) {
        const parent = stack.pop()
        screen = parent
          ? { ...parent, rows: result.rows, path: result.path || parent.path }
          : { ...screen, rows: result.rows, path: result.path || screen.path }
      }
      renderList()
      return
    }
    await activate()
  }

  function move(delta) {
    if (!screen || !screen.rows || !screen.rows.length) return
    const count = screen.rows.length
    screen.selected = (screen.selected + delta + count) % count
    renderList()
  }

  async function pageBy(delta) {
    if (!screen || !screen.paging) return
    const page = Math.min(screen.pages, Math.max(1, (screen.page || 1) + delta))
    const result = await session.call({ op: "history", page })
    screen = { ...screen, ...result, selected: 0 }
    renderList()
  }

  function onKey(key) {
    if (finished) return
    const name = key.name
    if (capture) {
      if (name === "escape") {
        capture = null
        renderList()
        return
      }
      if (name === "return") {
        const text = capture.text
        const index = screen.selected
        capture = null
        session
          .call({ op: "apply", path: screen.path, index, text })
          .then((result) => {
            if (result.rows) screen = { ...screen, rows: result.rows }
            renderList()
          })
          .catch(() => renderList())
        return
      }
      const parts = []
      if (key.ctrl) parts.push("ctrl")
      if (key.shift) parts.push("shift")
      if (key.option || key.meta) parts.push("alt")
      if (key.super) parts.push("cmd")
      parts.push(name === "space" ? "space" : name)
      capture.text = parts.join("+")
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
      rows: [{ action: String(error.message || error), path: "/", meta: "", kind: "note" }],
      selected: 0,
      context: [],
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
