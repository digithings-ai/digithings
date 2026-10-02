--- digivoice Hammerspoon sample adapter
--- Locked binds (do not invent others):
---   Right Option (61)           → dict toggle (press start / press stop → transcribe + paste)
---   Esc                         → cancel an active take (discard; no paste, no history)
---                                 Esc on a preview banner only hides the preview.
---   Double-tap Left Option (58) → speak --selection (fail soft; the grid is the status)
---
--- Status: a custom overlay banner (banner_core.lua) draws one status icon.
--- No status word, pin, button, transcript, or waveform. A click focuses the
--- digivoice terminal when it is already open, and opens it otherwise.
--- Esc still cancels a take. Drag moves the icon; release near an anchor snaps.
--- Retract (default) hides the icon when voice is idle. banner_pinned keeps it.
--- `digivoice banner show` still reveals a status preview with no dictation.
--- Banner enable/position/density/animations/pin live in settings.json
--- (`digivoice settings set banner_pinned true`) and are re-read per take.
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

local session = nil -- the one banner session on screen (dict, speak, or preview)
local canvas = nil
local frame_timer = nil
local hide_timer = nil
local theme_timer = nil
local drag_timer = nil
local hover_timer = nil
local scroll_tap = nil
local idle_timer = nil
local esc_tap = nil
local hover_seq = 0

-- Forward declarations: defined below their first use site.
local current_view
local ensure_scroll_tap
local ensure_esc_tap
local write_file
local end_session

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

local CELL_FIRST = 2 -- canvas element index of grid cell 0 (1 = background)

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

local function scroll_max(s, box)
  if s.density == "full" and box.clipped and box.all then
    return math.max(0, #box.all - #box.lines)
  end
  return 0
end

local function icon_phase_for(s, view)
  if core.should_draw(view.state, s.config.banner_pinned == true) then
    return core.icon_phase(view.state)
  end
  return ""
end

local function build_canvas(s, view, box)
  delete_canvas()
  local screen = hs.screen.mainScreen()
  if not screen then
    return
  end
  local chrome = core.theme_colors(s.theme)
  local canvas_h = box.h
  local origin = s.origin or core.resolve_position(s.config.banner_position, screen:frame(), box, core.MARGIN)
  s.origin = { x = origin.x, y = origin.y }
  s.size = { w = box.w, h = canvas_h }
  canvas = hs.canvas.new({ x = origin.x, y = origin.y, w = box.w, h = canvas_h })
  canvas:level(hs.canvas.windowLevels.overlay)
  -- The click focuses the terminal UI through the launcher. The overlay itself
  -- must not become the focused window.
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

  -- Icon only: the background holds the phase. The grid is the status mark.
  canvas:appendElements({
    {
      type = "rectangle",
      action = "strokeAndFill",
      fillColor = chrome.bg,
      strokeColor = chrome.border,
      strokeWidth = 1,
      trackMouseUp = true,
      trackMouseDown = true,
      trackMouseEnterExit = false,
      id = "background",
      phase = icon_phase_for(s, view),
      frame = { x = 0, y = 0, w = box.w, h = box.h },
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

  canvas:mouseCallback(function(_, message, id)
    if session ~= s then
      return
    end
    if message == "mouseDown" and id == "background" then
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
  local prev = { x = s.origin.x, y = s.origin.y, w = s.size.w, h = s.size.h }
  local next = core.reanchor(prev, { w = box.w, h = box.h }, s.anchor)
  s.origin = next
  build_canvas(s, view, box)
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
  local signature = table.concat({
    view.state,
    icon_phase_for(s, view),
    s.density,
    theme,
    tostring(s.config.banner_pinned),
  }, "\0")
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
      s.origin = core.reanchor(
        { x = s.origin.x, y = s.origin.y, w = s.size.w, h = s.size.h },
        { w = box.w, h = box.h },
        s.anchor
      )
    end
    build_canvas(s, view, box)
  else
    paint_cells(s, view)
    if canvas and canvas[1] then
      canvas[1].phase = icon_phase_for(s, view)
    end
  end
  ensure_scroll_tap(s, box)
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

--- Hide the canvas. Takes keep running; previews end. Esc still discards a take.
local function hide_banner(s)
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

local function tui_pid_text()
  local f = io.open(DATA_DIR .. "/tui.pid", "r")
  if not f then
    return ""
  end
  local text = f:read("*a") or ""
  f:close()
  return text
end

--- Tests replace this. The default calls M._executor and never starts a terminal
--- on its own, so a unit run cannot launch Terminal or Hammerspoon.
function M.launch_tui(action)
  local run = M._executor
  if run then
    run(action)
  end
end

function finish_click(s, _)
  local dragged = finish_drag(s)
  if dragged then
    return
  end
  if s.kind == "preview" and s.discarded then
    return
  end
  local action = core.focus_action(core.tui_is_open(tui_pid_text()))
  if M.launch_tui then
    M.launch_tui(action)
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

function end_session(s)
  if session ~= s then
    return
  end
  frame_timer = cancel_timer(frame_timer)
  hide_timer = cancel_timer(hide_timer)
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
    scroll = 0,
    hover = false,
    hidden = false,
    standby = false,
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
    -- A pin settles done into the idle icon. Retract hides when the take is done.
    local wait = core.linger_seconds(s.final.state, s.density, s.config.banner_pinned)
    if wait ~= nil then
      hide_timer = hs.timer.doAfter(wait, function()
        if session ~= s then
          return
        end
        if s.config.banner_pinned then
          s.final = nil
          s.local_state = "idle"
          s.standby = true
          s.signature = nil
          render(s)
          return
        end
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
      session.signature = nil
      render(session)
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

function write_file(path, text)
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
-- A standby banner (home launch, no task) is not a take and must not block this.
function M.speak_selection()
  if session and session.kind == "dict" and not session.standby then
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

--- True when the banner canvas is on screen. Home launch calls `M.ensure_banner`.
function M.banner_visible()
  return canvas ~= nil
end

function M.ensure_banner()
  local config = core.parse_settings(read_json(SETTINGS_FILE))
  if not config.live_banner then
    return "disabled"
  end
  if canvas ~= nil then
    return "visible"
  end
  if session and session.task and session.task.isRunning and session.task:isRunning() then
    start_frames(session)
    return canvas ~= nil and "shown" or "hidden"
  end
  -- Launch arms hotkeys. The banner stays hidden unless it is pinned.
  if not config.banner_pinned then
    return "armed"
  end
  local s = begin_session("dict")
  s.local_state = "idle"
  s.standby = true
  start_frames(s)
  if canvas ~= nil then
    return "shown"
  end
  return "hidden"
end

function M.start()
  tap:start()
  -- Poll the spawn flag so `digivoice banner show` reveals a status preview.
  -- Hidden until a take, a pin, or that flag.
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
