--- digivoice Hammerspoon sample adapter
--- Locked binds (do not invent others):
---   Right Option (61)           → dict toggle (press start / press stop → transcribe + paste)
---   Esc                         → cancel an active take (discard; no paste, no history)
---   Double-tap Left Option (58) → speak --selection (fail soft; banner says why)
---
--- Status: a custom overlay banner (banner_core.lua) draws what the digivoice CLI
--- writes to status.json. It is display only; the one control is Esc. The only
--- Hammerspoon notification is the launch toast listing the commands above.
--- Banner enable/position/animations live in digivoice's settings.json
--- (`digivoice settings set banner_position top-right`) and are re-read per take.
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
local MARK_PATH = script_dir() .. "assets/digivoice-mark.png"

-- Double-tap window for Left Option speak (seconds).
local DOUBLE_TAP_SEC = 0.35
local FRAME_SEC = 1 / 15

local session = nil -- the one banner session on screen (dict or speak)
local menubar = nil
local canvas = nil
local frame_timer = nil
local hide_timer = nil
local esc_tap = nil

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

--------------------------------------------------------------------------------
-- menubar mark (mic-in-use indicator; stays even when the banner is disabled)
--------------------------------------------------------------------------------

local function show_menubar(title)
  if not menubar then
    menubar = hs.menubar.new(true)
    if not menubar then
      return
    end
    local mark = hs.image.imageFromPath(MARK_PATH)
    if mark then
      mark:size({ w = 16, h = 16 })
      menubar:setIcon(mark, false)
    end
  end
  menubar:setTitle(title)
end

local function hide_menubar()
  if menubar then
    menubar:delete()
    menubar = nil
  end
end

--------------------------------------------------------------------------------
-- banner canvas
--------------------------------------------------------------------------------

local DOT_FIRST = 5 -- canvas element index of dot 0

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

local function dot_color(state, i, t, animate)
  local cfg = core.matrix_for(state)
  return {
    red = cfg.color.red,
    green = cfg.color.green,
    blue = cfg.color.blue,
    alpha = core.dot_alpha(state, i, t, animate),
  }
end

local function build_canvas(s, view, box)
  delete_canvas()
  local screen = hs.screen.mainScreen()
  if not screen then
    return
  end
  local origin = core.resolve_position(s.config.banner_position, screen:frame(), box, core.MARGIN)
  canvas = hs.canvas.new({ x = origin.x, y = origin.y, w = box.w, h = box.h })
  canvas:level(hs.canvas.windowLevels.overlay)
  -- A click only expands the text; it must never steal focus from the app being typed into.
  canvas:clickActivating(false)
  canvas:behavior(hs.canvas.windowBehaviors.canJoinAllSpaces)

  local hint_parts = {}
  if box.hint then
    hint_parts[#hint_parts + 1] = box.hint
  end
  if box.expandable then
    hint_parts[#hint_parts + 1] = s.expanded and "click: collapse" or "click: expand"
  end

  local cfg = core.matrix_for(view.state)
  local text_color = { red = 0.92, green = 0.95, blue = 0.96, alpha = 1 }
  canvas:appendElements({
    {
      type = "rectangle",
      action = "fill",
      roundedRectRadii = { xRadius = 10, yRadius = 10 },
      fillColor = { red = 0.07, green = 0.10, blue = 0.12, alpha = 0.94 },
      trackMouseUp = true,
      id = "background",
    },
    {
      type = "text",
      text = box.title,
      textColor = { red = cfg.color.red, green = cfg.color.green, blue = cfg.color.blue, alpha = 1 },
      textSize = core.FONT_SIZE,
      textAlignment = "left",
      frame = { x = box.text_x, y = core.PAD + 2, w = box.text_w * 0.55, h = 20 },
    },
    {
      type = "text",
      text = table.concat(hint_parts, " · "),
      textColor = { red = 0.62, green = 0.66, blue = 0.68, alpha = 1 },
      textSize = core.FONT_SIZE - 2,
      textAlignment = "right",
      frame = { x = box.text_x + box.text_w * 0.45, y = core.PAD + 3, w = box.text_w * 0.55, h = 18 },
    },
    {
      type = "text",
      text = box.body,
      textColor = text_color,
      textSize = core.FONT_SIZE,
      textAlignment = "left",
      frame = {
        x = box.text_x,
        y = core.PAD + core.HEAD_HEIGHT - 6,
        w = box.text_w,
        h = math.max(0, box.h - core.PAD - core.HEAD_HEIGHT - 2),
      },
    },
  })

  local pitch = core.ICON / core.GRID
  local radius = pitch * 0.33
  local t = hs.timer.secondsSinceEpoch()
  local dots = {}
  for i = 0, core.GRID * core.GRID - 1 do
    local row, col = i // core.GRID, i % core.GRID
    dots[#dots + 1] = {
      type = "circle",
      action = "fill",
      center = {
        x = core.PAD + pitch * (col + 0.5),
        y = core.PAD + pitch * (row + 0.5),
      },
      radius = radius,
      fillColor = dot_color(view.state, i, t, s.config.banner_animations),
    }
  end
  canvas:appendElements(dots)

  canvas:mouseCallback(function(_, message)
    if message == "mouseUp" and session then
      session.expanded = not session.expanded
      session.signature = nil
    end
  end)
  canvas:show()
end

local function paint_dots(s, view)
  if not canvas then
    return
  end
  local t = hs.timer.secondsSinceEpoch()
  for i = 0, core.GRID * core.GRID - 1 do
    canvas[DOT_FIRST + i].fillColor = dot_color(view.state, i, t, s.config.banner_animations)
  end
end

local function current_view(s)
  if s.final then
    return s.final
  end
  return core.pick_view(s.local_state, read_json(STATUS_FILE), s)
end

local function render(s)
  local view = current_view(s)
  if not s.config.live_banner then
    return
  end
  local box = core.layout(view, s.kind, s.expanded)
  local signature = table.concat({ view.state, box.body, tostring(s.expanded), tostring(box.hint) }, "\0")
  if signature ~= s.signature or not canvas then
    s.signature = signature
    build_canvas(s, view, box)
  else
    paint_dots(s, view)
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

local function end_session(s)
  if session ~= s then
    return
  end
  frame_timer = cancel_timer(frame_timer)
  hide_timer = cancel_timer(hide_timer)
  stop_esc_tap()
  delete_canvas()
  hide_menubar()
  session = nil
end

local function begin_session(kind)
  if session then
    end_session(session)
  end
  local s = {
    kind = kind,
    start_ms = now_ms(),
    local_state = "loading",
    expanded = false,
    config = core.parse_settings(read_json(SETTINGS_FILE)),
    task = nil,
    final = nil,
    signature = nil,
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
  render(s)
end

local function finish_session(s, exit_code, stdout, stderr)
  if session ~= s then
    return
  end
  frame_timer = cancel_timer(frame_timer)
  stop_esc_tap()
  hide_menubar()
  s.final =
    core.final_view(exit_code, read_json(STATUS_FILE), s, stdout, stderr, s.local_state == "cancelling")
  if s.final.state == "error" then
    print("digivoice " .. s.kind .. " failed: " .. (s.final.detail or ""))
  end
  if s.config.live_banner then
    s.signature = nil
    render(s)
    hide_timer = hs.timer.doAfter(core.linger_seconds(s.final.state), function()
      end_session(s)
    end)
  else
    end_session(s)
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
  s.local_state = "cancelling"
  stop_esc_tap()
  -- The CLI polls the cancel-file; it kills the recorder / whisper and deletes the wav.
  if not write_file(CANCEL_FILE, "cancel\n") then
    pcall(function()
      s.task:kill9()
    end)
  end
  show_menubar(" …")
  render(s)
  return true
end

local function ensure_esc_tap()
  if not esc_tap then
    esc_tap = hs.eventtap.new({ hs.eventtap.event.types.keyDown }, function(event)
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
  show_menubar(" REC")
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
  show_menubar(" …")
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
  -- The one allowed notification: what is armed, and which CLI it will run.
  hs.notify.new({ title = "digivoice", informativeText = core.launch_notice(DIGIVOICE) }):send()
  print("digivoice: armed; cli = " .. DIGIVOICE)
end

function M.stop()
  tap:stop()
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
