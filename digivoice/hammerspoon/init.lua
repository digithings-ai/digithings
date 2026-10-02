--- digivoice Hammerspoon sample adapter
--- Hotkeys come from settings.json `hotkey_bindings` (hotkeys.lua).
--- Defaults, until a row is saved:
---   Right Option (61)           → dict toggle (press start / press stop → transcribe + paste)
---   Esc                         → cancel an active take (discard; no paste, no history)
---                                 Esc on a preview banner only hides the preview.
---   Double-tap Left Option (58) → speak --selection (fail soft; the grid is the status)
--- A saved remap replaces that bind. The previous key is not also kept.
--- The file is re-read when it changes, and again on hs.reload().
--- A binding that does not parse keeps the previous one and prints a warning.
---
--- Status: a custom overlay banner (banner_core.lua) draws one status icon.
--- No status word, copy, close, pin button, or transcript. Recording is a
--- level meter on the grid; the other marks move. banner_animations false
--- holds one frame. A click focuses the digivoice terminal when it is already
--- open, and opens it otherwise.
--- The cancel bind still cancels a take. Drag moves the icon; release near an anchor snaps.
--- Off hides the icon when voice is idle. banner_pinned keeps it. Density is ignored.
--- `digivoice banner show` still reveals a status preview with no dictation.
--- Banner enable/position/animations/pin live in settings.json
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
local hotkeys = dofile(script_dir() .. "hotkeys.lua")

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
local CAPTURE_FILE = DATA_DIR .. "/hotkey.capture"
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
local idle_timer = nil
local esc_tap = nil

-- Forward declarations: defined below their first use site.
local current_view
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

local function cell_color(state, i, t, animate)
  local cfg = core.matrix_for(state)
  return {
    red = cfg.color.red,
    green = cfg.color.green,
    blue = cfg.color.blue,
    alpha = core.dot_alpha(state, i, t, animate),
  }
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
  -- One window only: the icon. Disable the window shadow when the host exposes it.
  pcall(function()
    canvas:shadow(false)
  end)

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
  local box = core.layout(view)
  s.box = box
  local prev = { x = s.origin.x, y = s.origin.y, w = s.size.w, h = s.size.h }
  local next = core.reanchor(prev, { w = box.w, h = box.h }, s.anchor)
  s.origin = next
  build_canvas(s, view, box)
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

local function flag_pending()
  local flag = read_json(FLAG_FILE)
  return type(flag) == "table" and flag.pending == true
end

local function render(s)
  local view = current_view(s)
  local pending = s.pending == true or flag_pending()
  if s.hidden or not s.config.live_banner
    or not core.should_draw(view.state, s.config.banner_pinned == true, pending) then
    if canvas then
      delete_canvas()
      s.signature = nil
    end
    return
  end
  local screen = hs.screen.mainScreen()
  if not screen then
    return
  end
  local frame = screen:frame()
  local box = core.layout(view)
  s.box = box
  local theme = detect_theme()
  local signature = table.concat({
    view.state,
    icon_phase_for(s, view),
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
  drag_timer = cancel_timer(drag_timer)
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
  drag_timer = cancel_timer(drag_timer)
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
    config = config,
    theme = detect_theme(),
    task = nil,
    final = nil,
    signature = nil,
    origin = nil,
    anchor = nil,
    box = nil,
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
    local wait = core.linger_seconds(s.final.state, s.config.banner_pinned)
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
  if flag and flag.pending == true then
    return
  end
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
    print("digivoice: could not write " .. CANCEL_FILE .. "; take continues (the dictation key stops it)")
    return false
  end
  s.local_state = "cancelling"
  stop_esc_tap()
  render(s)
  return true
end

ensure_esc_tap = function()
  -- Cancel is the hotkey tap below, armed for the whole session.
  -- A separate Esc tap would keep the old key after a remap.
end

local function focus_argv()
  if not hs.application or not hs.application.frontmostApplication then
    return {}
  end
  local app = hs.application.frontmostApplication()
  if type(app) ~= "table" then
    return {}
  end
  local name = app.name and app:name() or ""
  local bundle = app.bundleID and app:bundleID() or ""
  if name == "" and bundle == "" then
    return {}
  end
  return { "--focus-name", tostring(name), "--focus-bundle", tostring(bundle) }
end

local function start_dict()
  hs.fs.mkdir(DATA_DIR)
  os.remove(STOP_FILE)
  os.remove(CANCEL_FILE)
  local argv = { "dict", "--toggle", "--stop-file", STOP_FILE }
  for _, part in ipairs(focus_argv()) do
    argv[#argv + 1] = part
  end
  local s = begin_session("dict")
  s.task = hs.task.new(DIGIVOICE, function(exit_code, std_out, std_err)
    finish_session(s, exit_code, std_out, std_err)
  end, argv)
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
  local argv = { "speak", "--selection" }
  for _, part in ipairs(focus_argv()) do
    argv[#argv + 1] = part
  end
  local s = begin_session("speak")
  s.task = hs.task.new(DIGIVOICE, function(exit_code, std_out, std_err)
    finish_session(s, exit_code, std_out, std_err)
  end, argv)
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
-- hotkeys (settings.json hotkey_bindings; defaults until a row is saved)
--------------------------------------------------------------------------------

local binds = hotkeys.defaults()
local binds_sig = nil
local warned_hotkey = {}
local modifier_down = {}
local last_double = {}

local function refresh_hotkeys()
  local ok_read, text = pcall(function()
    local f = io.open(SETTINGS_FILE, "r")
    if not f then
      return ""
    end
    local body = f:read("*a") or ""
    f:close()
    return body
  end)
  if not ok_read then
    print("digivoice: could not read settings.json; keeping hotkeys")
    return
  end
  if text == binds_sig then
    return
  end
  binds_sig = text
  local raw = nil
  if text ~= "" then
    local ok_json, decoded = pcall(read_json, SETTINGS_FILE)
    if not ok_json or decoded == nil then
      print("digivoice: settings.json did not parse; keeping hotkeys")
      return
    end
    raw = decoded
  end
  local extracted = hotkeys.bindings_from_settings(raw)
  local next_binds, warnings = hotkeys.apply(binds, extracted)
  binds = next_binds
  for _, warning in ipairs(warnings) do
    if not warned_hotkey[warning] then
      warned_hotkey[warning] = true
      print("digivoice: " .. warning)
    end
  end
end

local function flag_is_down(keycode, flags)
  if keycode == 58 or keycode == 61 then
    return flags.alt == true
  end
  if keycode == 54 or keycode == 55 then
    return flags.cmd == true
  end
  if keycode == 56 or keycode == 60 then
    return flags.shift == true
  end
  if keycode == 59 or keycode == 62 then
    return flags.ctrl == true
  end
  return false
end

local function flag_edge(keycode, flags)
  local down = flag_is_down(keycode, flags)
  local was = modifier_down[keycode] == true
  modifier_down[keycode] = down
  return down and not was
end

local function double_ready(role)
  local now = hs.timer.secondsSinceEpoch()
  local prev = last_double[role] or 0
  if prev > 0 and (now - prev) <= DOUBLE_TAP_SEC then
    last_double[role] = 0
    return true
  end
  last_double[role] = now
  return false
end

local function plain_esc(spec)
  return spec.kind == "key"
    and spec.keycode == 53
    and not spec.ctrl
    and not spec.shift
    and not spec.alt
    and not spec.cmd
end

local function run_hotkey(role, spec)
  if role == "cancel" then
    if session and session.kind == "preview" then
      M.hide_preview()
      return true
    end
    if M.cancel_dict() then
      return true
    end
    -- Plain Esc with nothing to cancel still reaches the focused app.
    if plain_esc(spec) then
      return false
    end
    return spec.kind == "key"
  end
  if role == "dictation" then
    M.toggle_dict()
  else
    M.speak_selection()
  end
  -- Swallow a real key so a chord does not also type. Modifier taps pass through.
  return spec.kind == "key"
end

--- Option-key binds use alt as the down/up edge. A release has alt false, so it
--- must still match or the next press looks like the key never came up.
local function flags_binding(spec, keycode, flags)
  if spec.kind ~= "flags" or spec.keycode ~= keycode then
    return false
  end
  return (flags.ctrl == true) == spec.ctrl
    and (flags.shift == true) == spec.shift
    and (flags.cmd == true) == spec.cmd
end

local function handle_hotkey(event)
  local kind = event:getType()
  local event_kind
  if kind == hs.eventtap.event.types.flagsChanged then
    event_kind = "flags"
  elseif kind == hs.eventtap.event.types.keyDown then
    event_kind = "key"
  else
    return false
  end
  if event_kind == "key" and type(event.isARepeat) == "function" and event:isARepeat() then
    return false
  end
  local keycode = event:getKeyCode()
  local flags = event:getFlags() or {}
  for _, role in ipairs({ "cancel", "dictation", "speak" }) do
    local spec = binds[role]
    local hit = false
    if spec and spec.kind == event_kind then
      if event_kind == "flags" then
        hit = flags_binding(spec, keycode, flags)
      else
        hit = hotkeys.matches(spec, keycode, flags)
      end
    end
    if hit then
      if event_kind == "flags" and not flag_edge(keycode, flags) then
        return false
      end
      if spec.double and not double_ready(role) then
        return false
      end
      return run_hotkey(role, spec)
    end
  end
  return false
end

--- Body of hotkey.capture, or "" when the field is closed or the read fails.
local function capture_flag()
  local ok, text = pcall(function()
    local f = io.open(CAPTURE_FILE, "r")
    if not f then
      return ""
    end
    local body = f:read("*a") or ""
    f:close()
    return body
  end)
  if not ok or type(text) ~= "string" then
    return ""
  end
  return text
end

-- flagsChanged is types[1] so existing tests still find this tap.
-- keyDown is the same tap: one listener, replaced when a remap is saved.
-- While the hotkey field is open, the key is returned to the terminal.
local tap = hs.eventtap.new({
  hs.eventtap.event.types.flagsChanged,
  hs.eventtap.event.types.keyDown,
}, function(event)
  local ok, result = pcall(function()
    refresh_hotkeys()
    if hotkeys.suspended(capture_flag()) then
      return false
    end
    return handle_hotkey(event)
  end)
  if not ok then
    print("digivoice: hotkey error: " .. tostring(result))
    return false
  end
  return result == true
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
  refresh_hotkeys()
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
  drag_timer = cancel_timer(drag_timer)
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
