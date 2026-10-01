--- digivoice Hammerspoon sample adapter
--- Locked binds (do not invent others):
---   Right Option (61)           → dict toggle (press start / press stop → transcribe + paste)
---   Esc                         → cancel an active take (discard; no paste, no history)
---                                 Esc on a preview banner only hides the preview.
---   Double-tap Left Option (58) → speak --selection (fail soft; banner says why)
---
--- Status: a custom overlay banner (banner_core.lua) draws what the digivoice CLI
--- writes to status.json. It is display only: no title chrome, no hints, no
--- settings UI — a click cycles density mini → peek → full, Esc cancels a take.
--- Ship model: background only — no Dock icon, no digivoice menubar mark, no
--- launch toast. Customize and Quit live in the digivoice TUI (Quit tears HS down;
--- closing the Terminal alone leaves Hammerspoon running).
--- Hover shows icon-only copy + close below the banner (stacked when mini,
--- right-aligned row when wider). Drag moves it freely; release near one of the
--- 9 anchors snaps and persists the position. Text types in fast (9ms/char);
--- peek→full continues the caret, collapse/close hides instantly (no reverse).
--- Full caps near half the screen height and wheel-scrolls with no scrollbar.
--- The banner is hidden by default: takes spawn it, or spawn a preview without
--- any dictation via `digivoice banner show` (CLI) / M.spawn_preview() (console).
--- Banner enable/position/density/animations live in digivoice's settings.json
--- (`digivoice settings set banner_density full`) and are re-read per take.
--- Install: see README.md in this directory.
--- This file is a sample outside the Python package import path.

local M = {}

local function script_dir()
  local info = debug.getinfo(1, "S")
  local src = info and info.source or ""
  if src:sub(1, 1) == "@" then
    src = src:sub(2)
  end
  return src:match("(.*/)") or "./"
end

local core = dofile(script_dir() .. "banner_core.lua")

local function executable(path)
  local f = io.open(path, "r")
  if f then
    f:close()
    return true
  end
  return false
end

local function shell_lookup(command)
  local handle = io.popen(command .. " 2>/dev/null")
  if not handle then
    return nil
  end
  local found = handle:read("*l")
  handle:close()
  if found and found ~= "" then
    return found
  end
  return nil
end

-- Hammerspoon's own PATH is short, so look in the places a uv/pip install lands.
local function digivoice_bin()
  local from_env = os.getenv("DIGIVOICE_BIN")
  if from_env and from_env ~= "" then
    return from_env
  end
  local found = shell_lookup("command -v digivoice")
  if found then
    return found
  end
  local home = os.getenv("HOME") or ""
  local candidates = {}
  -- <repo>/.venv/bin/digivoice when this folder is a symlink into the checkout.
  local real = hs.fs and hs.fs.pathToAbsolute and hs.fs.pathToAbsolute(script_dir())
  if real then
    candidates[#candidates + 1] = real:gsub("/+$", "") .. "/../../.venv/bin/digivoice"
  end
  candidates[#candidates + 1] = home .. "/.local/bin/digivoice"
  candidates[#candidates + 1] = home .. "/.venv/bin/digivoice"
  for _, path in ipairs(candidates) do
    if executable(path) then
      return path
    end
  end
  local login = shell_lookup((os.getenv("SHELL") or "/bin/zsh") .. " -lc 'command -v digivoice'")
  return login or "digivoice"
end

local function data_dir()
  local override = os.getenv("DIGIVOICE_DATA_DIR")
  if override and override ~= "" then
    return override
  end
  return (os.getenv("HOME") or "") .. "/Library/Application Support/digivoice"
end

local DIGIVOICE = digivoice_bin()
local DATA_DIR = data_dir()
local STOP_FILE = DATA_DIR .. "/dict.stop"
local CANCEL_FILE = DATA_DIR .. "/dict.cancel"
local STATUS_FILE = DATA_DIR .. "/status.json"
local SETTINGS_FILE = DATA_DIR .. "/settings.json"
local POS_FILE = DATA_DIR .. "/banner_pos.json"
local FLAG_FILE = DATA_DIR .. "/banner.show"

-- Double-tap window for Left Option speak (seconds).
local DOUBLE_TAP_SEC = 0.35
local FRAME_SEC = 1 / 15
local TW_STEP = 1

local session = nil -- the one banner session on screen (dict, speak, or preview)
local canvas = nil
local frame_timer = nil
local hide_timer = nil
local tw_timer = nil
local theme_timer = nil
local drag_timer = nil
local hover_timer = nil
local scroll_tap = nil
local idle_timer = nil
local esc_tap = nil
local hover_seq = 0

-- Forward declarations: defined below their first use site.
local current_view
local ensure_tw
local ensure_scroll_tap
local ensure_esc_tap

local function now_ms()
  return math.floor(hs.timer.secondsSinceEpoch() * 1000)
end

local function read_json(path)
  local ok, value = pcall(hs.json.read, path)
  if ok and type(value) == "table" then
    return value
  end
  return nil
end

--- DigiChat light/dark flip. Tests pin DIGIVOICE_THEME; on a Mac we read the
--- system appearance. RYG status colors stay — only banner chrome flips.
local function detect_theme()
  local override = os.getenv("DIGIVOICE_THEME")
  if override == "light" or override == "dark" then
    return override
  end
  local found = shell_lookup("defaults read -g AppleInterfaceStyle")
  if found and found:find("Dark") then
    return "dark"
  end
  return "light"
end

local function load_saved_pos()
  return read_json(POS_FILE)
end

local function save_pos(pos)
  local f = io.open(POS_FILE, "w")
  if not f then
    return false
  end
  local anchor = pos.anchor and (', "anchor": "' .. tostring(pos.anchor) .. '"') or ""
  f:write('{"x": ' .. tostring(pos.x) .. ', "y": ' .. tostring(pos.y) .. anchor .. "}\n")
  f:close()
  return true
end

local function clear_flag()
  local f = io.open(FLAG_FILE, "w")
  if f then
    f:write('{"visible": false}\n')
    f:close()
  end
end

--------------------------------------------------------------------------------

--------------------------------------------------------------------------------
-- banner canvas
--------------------------------------------------------------------------------

local CELL_FIRST = 3 -- canvas element index of grid cell 0 (1 = background, 2 = body)
local BODY_INDEX = 2

local function delete_canvas()
  if canvas then
    canvas:delete()
    canvas = nil
  end
end

local function cancel_timer(timer)
  if timer then
    timer:stop()
  end
  return nil
end

local function stop_tw()
  tw_timer = cancel_timer(tw_timer)
end

local function stop_scroll_tap()
  if scroll_tap then
    scroll_tap:stop()
    scroll_tap = nil
  end
end

local function cell_color(state, i, t, animate)
  local cfg = core.matrix_for(state)
  return {
    red = cfg.color.red,
    green = cfg.color.green,
    blue = cfg.color.blue,
    alpha = core.dot_alpha(state, i, t, animate),
  }
end

--- Typewriter target: full scrolls over all lines; peek/mini reveal the glimpse.
local function tw_target(s, box)
  if s.density == "full" and box.clipped and box.all and #box.all > 0 then
    return table.concat(box.all, "\n")
  end
  return box.body
end

local function split_lines(text)
  local out = {}
  for line in (tostring(text or "") .. "\n"):gmatch("(.-)\r?\n") do
    out[#out + 1] = line
  end
  if #out > 0 and out[#out] == "" then
    out[#out] = nil
  end
  return out
end

--- Currently visible body text: typewriter prefix, then the scroll window.
local function visible_text(s, box)
  local revealed = core.tw_slice(s.tw_target or box.body, s.caret or 0).shown
  if s.density == "full" and box.clipped then
    local rows = split_lines(revealed)
    local size = math.max(1, #box.lines)
    local max_top = math.max(0, #rows - size)
    local top = math.min(s.scroll or 0, max_top)
    s.scroll = top
    local win = {}
    for i = top + 1, math.min(top + size, #rows) do
      win[#win + 1] = rows[i]
    end
    return table.concat(win, "\n")
  end
  return revealed
end

local function scroll_max(s, box)
  if s.density == "full" and box.clipped and box.all then
    return math.max(0, #box.all - #box.lines)
  end
  return 0
end

local function icon_copy(x, y, color, id)
  -- Two overlapping outline squares (pure vector, no font glyph needed).
  local s = core.CTRL_SIZE
  return {
    { type = "rectangle", action = "stroke", strokeColor = color, strokeWidth = 1.2,
      frame = { x = x + 4, y = y + 5, w = s - 9, h = s - 9 }, id = id },
    { type = "rectangle", action = "stroke", strokeColor = color, strokeWidth = 1.2,
      frame = { x = x + 6, y = y + 3, w = s - 9, h = s - 9 }, id = id },
  }
end

local function icon_close(x, y, color, id)
  local s = core.CTRL_SIZE
  return {
    { type = "segments", action = "stroke", strokeColor = color, strokeWidth = 1.2,
      coordinates = { { x = x + 5, y = y + 5 }, { x = x + s - 5, y = y + s - 5 } }, id = id },
    { type = "segments", action = "stroke", strokeColor = color, strokeWidth = 1.2,
      coordinates = { { x = x + s - 5, y = y + 5 }, { x = x + 5, y = y + s - 5 } }, id = id },
  }
end

local function build_canvas(s, view, box)
  delete_canvas()
  local screen = hs.screen.mainScreen()
  if not screen then
    return
  end
  local chrome = core.theme_colors(s.theme)
  local hover = s.hover
  local controls = hover and core.controls_layout(box.w, box.h, s.density) or nil
  local canvas_h = box.h + (hover and core.controls_height(s.density) or 0)
  local origin = s.origin or core.resolve_position(s.config.banner_position, screen:frame(), box, core.MARGIN)
  s.origin = { x = origin.x, y = origin.y }
  s.size = { w = box.w, h = canvas_h }
  canvas = hs.canvas.new({ x = origin.x, y = origin.y, w = box.w, h = canvas_h })
  canvas:level(hs.canvas.windowLevels.overlay)
  -- A click only cycles density; it must never steal focus from the app being typed into.
  canvas:clickActivating(false)
  canvas:behavior(hs.canvas.windowBehaviors.canJoinAllSpaces)
  -- One window only: banner + controls share this canvas. Never a second
  -- canvas/window for the buttons. Disable the window shadow when the host
  -- exposes it so the 18px pills read as chrome of this float unit instead
  -- of independent floating canvases (mock .float-root, not windows).
  pcall(function()
    canvas:shadow(false)
  end)

  -- Banner face stays box.h. The control gutter below (CTRL_GAP + pills) is
  -- transparent canvas: sibling chrome of the same float unit, never a
  -- stretch of the banner fill/stroke (mock .banner + .controls-under).

  -- No chrome: background + body text only. State reads from the grid alone.
  canvas:appendElements({
    {
      type = "rectangle",
      action = "strokeAndFill",
      fillColor = chrome.bg,
      strokeColor = chrome.border,
      strokeWidth = 1,
      trackMouseUp = true,
      trackMouseDown = true,
      trackMouseEnterExit = true,
      id = "background",
      frame = { x = 0, y = 0, w = box.w, h = box.h },
    },
    {
      type = "text",
      text = visible_text(s, box),
      textColor = chrome.text,
      textSize = core.FONT_SIZE,
      textFont = "Menlo",
      textAlignment = "left",
      id = "body",
      frame = {
        x = box.text_x,
        y = core.PAD,
        w = box.text_w,
        h = math.max(0, box.h - core.PAD * 2),
      },
    },
  })

  -- DigiChat-style square status grid, top-left.
  local t = hs.timer.secondsSinceEpoch()
  local cells = {}
  for i = 0, core.GRID * core.GRID - 1 do
    local frame = core.cell_box(i)
    cells[#cells + 1] = {
      type = "rectangle",
      action = "fill",
      frame = frame,
      fillColor = cell_color(view.state, i, t, s.config.banner_animations),
    }
  end
  canvas:appendElements(cells)

  -- Hover: icon-only copy + close below the banner.
  if controls then
    for _, btn in ipairs(controls.buttons) do
      canvas:appendElements({
        {
          type = "rectangle",
          action = "strokeAndFill",
          fillColor = chrome.bg,
          strokeColor = chrome.border,
          strokeWidth = 1,
          trackMouseUp = true,
          trackMouseEnterExit = true,
          id = btn.id,
          frame = { x = btn.x, y = btn.y, w = btn.w, h = btn.h },
        },
      })
      local parts
      if btn.id == "copy" then
        parts = icon_copy(btn.x, btn.y, chrome.text, btn.id)
      else
        parts = icon_close(btn.x, btn.y, chrome.text, btn.id)
      end
      canvas:appendElements(parts)
    end
  end

  canvas:mouseCallback(function(_, message, id)
    if session ~= s then
      return
    end
    if message == "mouseEnter" then
      hover_seq = hover_seq + 1
      hover_timer = cancel_timer(hover_timer)
      if not s.hover then
        s.hover = true
        rebuild(s)
      end
    elseif message == "mouseExit" then
      local seen = hover_seq + 1
      hover_seq = seen
      hover_timer = cancel_timer(hover_timer)
      hover_timer = hs.timer.doAfter(0.25, function()
        if session ~= s or hover_seq ~= seen or not s.hover then
          return
        end
        -- Same-canvas chrome: banner face, the CTRL_GAP gutter, and the pills
        -- are one window. Moving pointer banner<->controls (or pausing in the
        -- transparent gap, which fires exit with no enter) must not dismiss.
        local ok, pos = pcall(hs.mouse.getAbsolutePosition)
        if ok and pos and s.origin and s.size then
          if
            pos.x >= s.origin.x
            and pos.x < s.origin.x + s.size.w
            and pos.y >= s.origin.y
            and pos.y < s.origin.y + s.size.h
          then
            return
          end
        end
        s.hover = false
        rebuild(s)
      end)
    elseif message == "mouseDown" and id == "background" then
      start_drag(s)
    elseif message == "mouseUp" then
      finish_click(s, id)
    end
  end)
  canvas:show()
end

--- Rebuild the canvas in place, keeping the pin so growth heads outward.
function rebuild(s)
  if not canvas then
    return
  end
  local screen = hs.screen.mainScreen()
  if not screen then
    return
  end
  local view = current_view(s)
  local box = core.layout(view, s.kind, s.density, { screen_h = screen:frame().h })
  s.box = box
  s.tw_target = tw_target(s, box)
  if not s.config.banner_animations then
    s.caret = #s.tw_target
  else
    s.caret = math.min(s.caret or 0, #s.tw_target)
  end
  local prev = { x = s.origin.x, y = s.origin.y, w = s.size.w, h = s.size.h }
  local extra = s.hover and core.controls_height(s.density) or 0
  local next = core.reanchor(prev, { w = box.w, h = box.h + extra }, s.anchor)
  s.origin = next
  build_canvas(s, view, box)
  ensure_tw(s)
  ensure_scroll_tap(s, box)
end

local function paint_cells(s, view)
  if not canvas then
    return
  end
  local t = hs.timer.secondsSinceEpoch()
  for i = 0, core.GRID * core.GRID - 1 do
    canvas[CELL_FIRST + i].fillColor = cell_color(view.state, i, t, s.config.banner_animations)
  end
end

current_view = function(s)
  if s.kind == "preview" then
    return { state = "recording", text = s.preview_text or "", detail = "" }
  end
  if s.final then
    return s.final
  end
  return core.pick_view(s.local_state, read_json(STATUS_FILE), s)
end

local function render(s)
  local view = current_view(s)
  if s.hidden or not s.config.live_banner then
    return
  end
  local screen = hs.screen.mainScreen()
  if not screen then
    return
  end
  local frame = screen:frame()
  local box = core.layout(view, s.kind, s.density, { screen_h = frame.h })
  s.box = box
  local theme = detect_theme()
  local target = tw_target(s, box)
  if target ~= s.tw_target then
    -- New text extends the target; the caret continues (no restart).
    s.tw_target = target
    s.caret = math.min(s.caret or 0, #target)
  end
  if not s.config.banner_animations then
    s.caret = #target
  end
  local signature = table.concat({ view.state, target, s.density, theme, tostring(s.hover) }, "\0")
  if signature ~= s.signature or not canvas then
    s.signature = signature
    s.theme = theme
    if not s.origin then
      local saved = core.resolve_saved(load_saved_pos(), frame, box, core.MARGIN)
      if saved then
        s.origin = { x = saved.x, y = saved.y }
        s.anchor = saved.anchor
      else
        s.origin = core.resolve_position(s.config.banner_position, frame, box, core.MARGIN)
        s.anchor = core.anchor_for_position(s.config.banner_position)
      end
    else
      -- Keep the pin across takes/text updates so growth heads outward.
      local extra = s.hover and core.controls_height(s.density) or 0
      s.origin = core.reanchor(
        { x = s.origin.x, y = s.origin.y, w = s.size.w, h = s.size.h },
        { w = box.w, h = box.h + extra },
        s.anchor
      )
    end
    build_canvas(s, view, box)
    ensure_tw(s)
  else
    paint_cells(s, view)
    if canvas then
      canvas[BODY_INDEX].text = visible_text(s, box)
    end
  end
  ensure_scroll_tap(s, box)
end

--------------------------------------------------------------------------------
-- typewriter: fast reveal, peek→full continues, collapse/close is instant
--------------------------------------------------------------------------------

ensure_tw = function(s)
  stop_tw()
  if not s.config.banner_animations then
    return
  end
  if (s.caret or 0) >= #(s.tw_target or "") then
    return
  end
  tw_timer = hs.timer.doEvery(core.TW_SEC, function()
    if session ~= s or not canvas then
      stop_tw()
      return
    end
    s.caret = math.min(#(s.tw_target or ""), (s.caret or 0) + TW_STEP)
    canvas[BODY_INDEX].text = visible_text(s, s.box)
    if s.caret >= #(s.tw_target or "") then
      stop_tw()
    end
  end)
end

--- Collapse to a smaller density: instant clip, no reverse typewriter.
local function collapse_to(s, density)
  stop_tw()
  s.density = density
  s.hover = false
  s.scroll = 0
  s.tw_target = nil
  s.caret = 1e9 -- reveal everything instantly; tw_slice clamps.
  s.signature = nil
  render(s)
end

local function cycle_density(s)
  local next = core.next_density(s.density)
  local order = { mini = 0, peek = 1, full = 2 }
  if (order[next] or 0) < (order[s.density] or 0) then
    collapse_to(s, next)
  else
    -- Expand: keep the caret so peek→full continues mid-stream.
    s.density = next
    s.scroll = 0
    s.signature = nil
    render(s)
    ensure_tw(s)
  end
end

--------------------------------------------------------------------------------
-- drag free + snap near 9 anchors + persist
--------------------------------------------------------------------------------

function start_drag(s)
  if s.drag then
    return
  end
  local mouse = hs.mouse and hs.mouse.getAbsolutePosition and hs.mouse.getAbsolutePosition()
  if not mouse then
    return
  end
  s.drag = { mx0 = mouse.x, my0 = mouse.y, ox = s.origin.x, oy = s.origin.y, moved = false }
  drag_timer = cancel_timer(drag_timer)
  drag_timer = hs.timer.doEvery(FRAME_SEC, function()
    if session ~= s or not s.drag or not canvas then
      drag_timer = cancel_timer(drag_timer)
      return
    end
    local pos = hs.mouse.getAbsolutePosition()
    local dx, dy = pos.x - s.drag.mx0, pos.y - s.drag.my0
    if math.sqrt(dx * dx + dy * dy) > 3 then
      s.drag.moved = true
    end
    local screen = hs.screen.mainScreen()
    if screen then
      local clamped = core.clamp_position(
        s.drag.ox + dx, s.drag.oy + dy, screen:frame(), s.size, core.MARGIN
      )
      s.origin = { x = clamped.x, y = clamped.y }
      canvas:topLeft({ x = clamped.x, y = clamped.y })
    end
    local buttons_ok, buttons = pcall(hs.eventtap.checkMouseButtons)
    if buttons_ok and buttons and not buttons.left then
      finish_drag(s)
    end
  end)
end

function finish_drag(s)
  drag_timer = cancel_timer(drag_timer)
  if not s.drag then
    return false
  end
  local was_moved = s.drag.moved
  s.drag = nil
  if was_moved and s.origin then
    local screen = hs.screen.mainScreen()
    if screen then
      local snapped = core.snap_position(
        s.origin.x, s.origin.y, screen:frame(), s.size, core.MARGIN
      )
      s.origin = { x = snapped.x, y = snapped.y }
      s.anchor = snapped.anchor
      if canvas then
        canvas:topLeft({ x = snapped.x, y = snapped.y })
      end
      save_pos(snapped)
    end
  end
  return was_moved
end

--------------------------------------------------------------------------------
-- hover controls: icon-only copy + close
--------------------------------------------------------------------------------

local function copy_body(text)
  -- Test hook: point DIGIVOICE_PBCOPY_FILE at a file to capture copies.
  local sink = os.getenv("DIGIVOICE_PBCOPY_FILE")
  if sink and sink ~= "" then
    local f = io.open(sink, "w")
    if f then
      f:write(tostring(text or ""))
      f:close()
      return true
    end
  end
  local p = io.popen("pbcopy", "w")
  if not p then
    return false
  end
  p:write(tostring(text or ""))
  p:close()
  return true
end

--- Close = instant hide (no reverse typewriter). Takes keep running silently;
--- previews end. Esc still discards a take; close never does.
local function hide_banner(s)
  stop_tw()
  stop_scroll_tap()
  drag_timer = cancel_timer(drag_timer)
  hover_timer = cancel_timer(hover_timer)
  delete_canvas()
  if s.kind == "preview" then
    if session == s then
      session = nil
    end
    clear_flag()
  else
    s.hidden = true
  end
end

--- Which control (if any) sits under the cursor. Fallback for hosts whose
--- mouseCallback does not pass the element id: same hit-test, same result.
local function hit_test(s)
  local mouse = hs.mouse and hs.mouse.getAbsolutePosition and hs.mouse.getAbsolutePosition()
  if not mouse or not s.origin or not s.box or not s.hover then
    return "background"
  end
  local layout = core.controls_layout(s.box.w, s.box.h, s.density)
  for _, btn in ipairs(layout.buttons) do
    local x, y = mouse.x - s.origin.x, mouse.y - s.origin.y
    if x >= btn.x and x < btn.x + btn.w and y >= btn.y and y < btn.y + btn.h then
      return btn.id
    end
  end
  return "background"
end

function finish_click(s, id)
  local dragged = finish_drag(s)
  if dragged then
    return -- a drag-drop never also clicks.
  end
  if id == nil then
    id = hit_test(s)
  end
  if id == "copy" then
    copy_body(s.tw_target or (s.box and s.box.body) or "")
  elseif id == "close" then
    hide_banner(s)
  else
    if s.kind == "preview" and s.discarded then
      return
    end
    cycle_density(s)
  end
end

--------------------------------------------------------------------------------
-- full scroll (≤50vh window, no scrollbar): wheel moves the line window
--------------------------------------------------------------------------------

ensure_scroll_tap = function(s, box)
  local need = s.density == "full" and box.clipped and not s.hidden
  if not need then
    stop_scroll_tap()
    return
  end
  if scroll_tap then
    return
  end
  local types = hs.eventtap.event.types
  local props = hs.eventtap.event.properties
  if not types or not types.scrollWheel or not props or not props.scrollWheelEventDeltaAxis1 then
    return
  end
  scroll_tap = hs.eventtap.new({ types.scrollWheel }, function(event)
    if session ~= s or not canvas or s.density ~= "full" or s.hidden then
      return false
    end
    local ok, delta = pcall(event.getProperty, event, props.scrollWheelEventDeltaAxis1)
    if not ok or type(delta) ~= "number" or delta == 0 then
      return false
    end
    local max = scroll_max(s, s.box or box)
    if max <= 0 then
      return false
    end
    local step = delta > 0 and -3 or 3
    local next = math.min(max, math.max(0, (s.scroll or 0) + step))
    if next == s.scroll then
      return false
    end
    s.scroll = next
    canvas[BODY_INDEX].text = visible_text(s, s.box or box)
    return true
  end)
  scroll_tap:start()
end

--------------------------------------------------------------------------------
-- session lifecycle
--------------------------------------------------------------------------------

local function stop_esc_tap()
  if esc_tap then
    esc_tap:stop()
  end
end

local function end_session(s)
  if session ~= s then
    return
  end
  frame_timer = cancel_timer(frame_timer)
  hide_timer = cancel_timer(hide_timer)
  stop_tw()
  stop_scroll_tap()
  drag_timer = cancel_timer(drag_timer)
  hover_timer = cancel_timer(hover_timer)
  theme_timer = cancel_timer(theme_timer)
  stop_esc_tap()
  delete_canvas()
  session = nil
end

local function begin_session(kind)
  if session then
    end_session(session)
  end
  local config = core.parse_settings(read_json(SETTINGS_FILE))
  local s = {
    kind = kind,
    start_ms = now_ms(),
    local_state = "loading",
    density = config.banner_density,
    config = config,
    theme = detect_theme(),
    task = nil,
    final = nil,
    signature = nil,
    origin = nil,
    anchor = nil,
    box = nil,
    caret = 0,
    tw_target = "",
    scroll = 0,
    hover = false,
    hidden = false,
    preview_text = "",
  }
  session = s
  return s
end

local function start_frames(s)
  if not s.config.live_banner then
    return
  end
  frame_timer = hs.timer.doEvery(FRAME_SEC, function()
    if session == s then
      render(s)
    end
  end)
  theme_timer = hs.timer.doEvery(2.0, function()
    if session == s then
      local theme = detect_theme()
      if theme ~= s.theme then
        s.signature = nil
        render(s)
      end
    end
  end)
  render(s)
end

local function finish_session(s, exit_code, stdout, stderr)
  if session ~= s then
    return
  end
  frame_timer = cancel_timer(frame_timer)
  theme_timer = cancel_timer(theme_timer)
  stop_esc_tap()
  s.final =
    core.final_view(exit_code, read_json(STATUS_FILE), s, stdout, stderr, s.local_state == "cancelling")
  if s.final.state == "error" then
    print("digivoice " .. s.kind .. " failed: " .. (s.final.detail or ""))
  end
  if s.hidden or not s.config.live_banner then
    end_session(s)
    return
  end
  if s.config.live_banner then
    s.signature = nil
    render(s)
    -- Full density stays until collapsed or removed; peek/mini auto-dismiss.
    local wait = core.linger_seconds(s.final.state, s.density)
    if wait ~= nil then
      hide_timer = hs.timer.doAfter(wait, function()
        end_session(s)
      end)
    end
  else
    end_session(s)
  end
end

--------------------------------------------------------------------------------
-- preview: hidden by default, spawn without any dictation
--------------------------------------------------------------------------------

--- Spawn a preview banner without starting dictation. Hidden by default;
--- call this (or `digivoice banner show`) to show one.
function M.spawn_preview(text)
  if session then
    return session
  end
  local s = begin_session("preview")
  s.preview_text = tostring(text or "")
  s.local_state = "recording"
  ensure_esc_tap()
  start_frames(s)
  return s
end

function M.hide_preview()
  if session and session.kind == "preview" then
    local s = session
    hide_banner(s)
    if session == s then
      end_session(s)
    end
    return true
  end
  return false
end

local function poll_flag()
  if session then
    -- A take owns the banner; a preview already showing needs no poll.
    if session.kind ~= "preview" then
      return
    end
    local flag = read_json(FLAG_FILE)
    if not flag or flag.visible == false then
      M.hide_preview()
    elseif type(flag.text) == "string" and flag.text ~= session.preview_text then
      session.preview_text = flag.text
      session.caret = 0
      session.signature = nil
      render(session)
      ensure_tw(session)
    end
    return
  end
  local flag = read_json(FLAG_FILE)
  if flag and flag.visible then
    M.spawn_preview(type(flag.text) == "string" and flag.text or "")
  end
end

--------------------------------------------------------------------------------
-- dictation
--------------------------------------------------------------------------------

local function write_file(path, text)
  local f = io.open(path, "w")
  if not f then
    return false
  end
  f:write(text)
  f:close()
  return true
end

function M.cancel_dict()
  local s = session
  if not s or s.kind ~= "dict" or not s.task or not s.task:isRunning() then
    return false
  end
  if not core.cancellable(s.kind, current_view(s).state) then
    return false
  end
  -- The CLI polls the cancel-file; it kills the recorder / whisper and deletes the wav.
  -- Never kill the CLI instead: its recorder runs in its own session and would be orphaned.
  if not write_file(CANCEL_FILE, "cancel\n") then
    print("digivoice: could not write " .. CANCEL_FILE .. "; take continues (Right Option stops it)")
    return false
  end
  s.local_state = "cancelling"
  stop_esc_tap()
  render(s)
  return true
end

ensure_esc_tap = function()
  if not esc_tap then
    esc_tap = hs.eventtap.new({ hs.eventtap.event.types.keyDown }, function(event)
      if session and session.kind == "preview" then
        -- Esc on a preview only hides it; nothing to discard.
        if core.is_cancel_key(event:getKeyCode(), event:getFlags()) then
          M.hide_preview()
          return true
        end
        return false
      end
      if core.is_cancel_key(event:getKeyCode(), event:getFlags()) then
        -- Swallow Esc only when it actually cancels a take.
        return M.cancel_dict()
      end
      return false
    end)
  end
  esc_tap:start()
end

local function start_dict()
  hs.fs.mkdir(DATA_DIR)
  os.remove(STOP_FILE)
  os.remove(CANCEL_FILE)
  local s = begin_session("dict")
  s.task = hs.task.new(DIGIVOICE, function(exit_code, std_out, std_err)
    finish_session(s, exit_code, std_out, std_err)
  end, { "dict", "--toggle", "--stop-file", STOP_FILE })
  if not s.task then
    end_session(s)
    print("digivoice: could not start digivoice dict (" .. DIGIVOICE .. ")")
    return
  end
  s.task:start()
  s.local_state = "recording"
  ensure_esc_tap()
  start_frames(s)
end

local function stop_dict(s)
  -- Touch the stop-file so digivoice ends sox/ffmpeg cleanly, then transcribes + pastes.
  -- The banner stays up until the task exits.
  if not write_file(STOP_FILE, "stop\n") then
    s.task:terminate()
  end
  s.local_state = "transcribing"
  render(s)
end

function M.toggle_dict()
  local s = session
  if s and s.kind == "dict" and s.task and s.task:isRunning() then
    -- Only the first press after "recording" stops; later presses are ignored.
    if s.local_state == "recording" or s.local_state == "loading" then
      stop_dict(s)
    end
    return
  end
  start_dict()
end

--------------------------------------------------------------------------------
-- speak selection
--------------------------------------------------------------------------------

-- Speaks the current selection only (digivoice speak --selection).
-- Fails soft: the banner shows why (e.g. nothing selected). No clipboard/history fallback.
function M.speak_selection()
  if session and session.kind == "dict" then
    return
  end
  local s = begin_session("speak")
  s.task = hs.task.new(DIGIVOICE, function(exit_code, std_out, std_err)
    finish_session(s, exit_code, std_out, std_err)
  end, { "speak", "--selection" })
  if not s.task then
    end_session(s)
    print("digivoice: could not start digivoice speak (" .. DIGIVOICE .. ")")
    return
  end
  s.task:start()
  ensure_esc_tap()
  start_frames(s)
end

--------------------------------------------------------------------------------
-- hotkeys
--------------------------------------------------------------------------------

-- Right Option = 61 (dict). Left Option = 58 (double-tap speak).
local RIGHT_OPTION = 61
local LEFT_OPTION = 58
local right_option_down = false
local left_option_down = false
local left_option_last_tap = 0

local tap = hs.eventtap.new({ hs.eventtap.event.types.flagsChanged }, function(event)
  local flags = event:getFlags()
  local ctrl = flags.ctrl == true
  local shift = flags.shift == true
  local alt = flags.alt == true
  local keyCode = event:getKeyCode()

  -- Double-tap Left Option alone → speak selection. Single tap is a no-op.
  if keyCode == LEFT_OPTION and not ctrl and not shift then
    local is_down = alt
    if is_down and not left_option_down then
      left_option_down = true
      local now = hs.timer.secondsSinceEpoch()
      if left_option_last_tap > 0 and (now - left_option_last_tap) <= DOUBLE_TAP_SEC then
        left_option_last_tap = 0
        M.speak_selection()
      else
        left_option_last_tap = now
      end
    elseif not is_down then
      left_option_down = false
    end
    return false
  end

  -- Right Option alone → dict toggle on press.
  if keyCode == RIGHT_OPTION and not ctrl and not shift then
    local is_down = alt
    if is_down and not right_option_down then
      right_option_down = true
      M.toggle_dict()
    elseif not is_down then
      right_option_down = false
    end
  end
  return false
end)

function M.start()
  tap:start()
  -- Poll the spawn flag so `digivoice banner show` reveals a preview. Hidden
  -- by default: nothing draws until a take or a flag asks for it.
  idle_timer = hs.timer.doEvery(1.0, poll_flag)
  -- Background-only: hide the Hammerspoon Dock icon. No digivoice menubar mark,
  -- no launch toast (TUI is the sole chrome for customize / Quit).
  if hs.dockicon and hs.dockicon.hide then
    hs.dockicon.hide()
  end
  print("digivoice: armed; cli = " .. DIGIVOICE)
end

function M.stop()
  tap:stop()
  idle_timer = cancel_timer(idle_timer)
  stop_tw()
  stop_scroll_tap()
  drag_timer = cancel_timer(drag_timer)
  hover_timer = cancel_timer(hover_timer)
  theme_timer = cancel_timer(theme_timer)
  stop_esc_tap()
  local s = session
  if s and s.kind == "dict" and s.task and s.task:isRunning() then
    stop_dict(s)
  end
  if session then
    end_session(session)
  end
end

M.start()
return M
