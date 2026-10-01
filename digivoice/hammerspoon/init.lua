--- digivoice Hammerspoon sample adapter
--- Locked binds (do not invent others):
---   Right Option (61)           → dict toggle (press start / press stop → transcribe + paste)
---   Double-tap Left Option (58) → speak --selection (fail soft notify if nothing selected)
---
--- Live banner: persistent menubar (+ optional canvas) for the whole Right Option capture.
--- Install: see README.md in this directory.
--- This file is a sample outside the Python package import path.

local M = {}

local function digivoice_bin()
  local from_env = os.getenv("DIGIVOICE_BIN")
  if from_env and from_env ~= "" then
    return from_env
  end
  local handle = io.popen("command -v digivoice 2>/dev/null")
  if handle then
    local found = handle:read("*l")
    handle:close()
    if found and found ~= "" then
      return found
    end
  end
  local home = os.getenv("HOME") or ""
  for _, path in ipairs({
    home .. "/.local/bin/digivoice",
    home .. "/.venv/bin/digivoice",
  }) do
    local f = io.open(path, "r")
    if f then
      f:close()
      return path
    end
  end
  return "digivoice"
end

local function data_dir()
  local override = os.getenv("DIGIVOICE_DATA_DIR")
  if override and override ~= "" then
    return override
  end
  return (os.getenv("HOME") or "") .. "/Library/Application Support/digivoice"
end

local function script_dir()
  local info = debug.getinfo(1, "S")
  local src = info and info.source or ""
  if src:sub(1, 1) == "@" then
    src = src:sub(2)
  end
  return src:match("(.*/)") or "./"
end

local DIGIVOICE = digivoice_bin()
local STOP_FILE = data_dir() .. "/dict.stop"
local dict_task = nil
local MARK_PATH = script_dir() .. "assets/digivoice-mark.png"

-- Double-tap window for Left Option speak (seconds).
local DOUBLE_TAP_SEC = 0.35

-- Persistent live-dictation indicator (menubar + optional top canvas).
local menubar = nil
local banner = nil
local banner_timer = nil

local function notify(title, text)
  hs.notify.new({ title = title, informativeText = text or "" }):send()
end

local function hide_live_banner()
  if banner_timer then
    banner_timer:stop()
    banner_timer = nil
  end
  if banner then
    banner:delete()
    banner = nil
  end
  if menubar then
    menubar:delete()
    menubar = nil
  end
end

local function show_live_banner()
  hide_live_banner()
  menubar = hs.menubar.new(true)
  if not menubar then
    return
  end
  local mark = hs.image.imageFromPath(MARK_PATH)
  if mark then
    -- Template-ish small icon for the menubar.
    mark:size({ w = 16, h = 16 })
    menubar:setIcon(mark, false)
    menubar:setTitle(" REC")
  else
    menubar:setTitle("● digivoice REC")
  end
  menubar:setTooltip("digivoice recording — Right Option again to stop and paste")

  -- Top-of-screen canvas banner for the whole capture (not a one-shot toast).
  local screen = hs.screen.mainScreen()
  if screen then
    local frame = screen:frame()
    local width = 280
    local height = 28
    local x = frame.x + (frame.w - width) / 2
    local y = frame.y + 8
    banner = hs.canvas.new({ x = x, y = y, w = width, h = height })
    banner:appendElements({
      {
        type = "rectangle",
        action = "fill",
        roundedRectRadii = { xRadius = 8, yRadius = 8 },
        fillColor = { red = 0.08, green = 0.12, blue = 0.14, alpha = 0.92 },
      },
      {
        type = "text",
        text = "digivoice · recording…",
        textColor = { red = 0.08, green = 0.72, blue = 0.65, alpha = 1 },
        textSize = 13,
        textAlignment = "center",
        frame = { x = 0, y = 4, w = width, h = 20 },
      },
    })
    banner:level(hs.canvas.windowLevels.overlay)
    banner:show()
  end
end

local function start_dict()
  hs.fs.mkdir(data_dir())
  os.remove(STOP_FILE)
  show_live_banner()
  dict_task = hs.task.new(DIGIVOICE, function(exitCode, stdOut, stdErr)
    dict_task = nil
    hide_live_banner()
    if exitCode == 0 then
      local preview = (stdOut or ""):gsub("%s+$", "")
      if #preview > 80 then
        preview = preview:sub(1, 77) .. "..."
      end
      notify("digivoice", preview ~= "" and preview or "dictation done")
    else
      local err = (stdErr or ""):gsub("%s+$", "")
      notify("digivoice dict failed", err ~= "" and err or ("exit " .. tostring(exitCode)))
    end
  end, {
    "dict",
    "--toggle",
    "--stop-file",
    STOP_FILE,
  })
  if not dict_task then
    hide_live_banner()
    notify("digivoice", "could not start digivoice dict")
    return
  end
  dict_task:start()
  -- Keep a one-shot toast in addition to the persistent banner so first-run is obvious.
  notify("digivoice", "recording… (Right Option again to stop)")
end

local function stop_dict()
  -- Touch the stop-file so digivoice ends sox/ffmpeg cleanly, then
  -- transcribes + pastes. Prefer stop-file over killing the process.
  -- Banner stays up until the task callback (transcribe/paste) finishes.
  local f = io.open(STOP_FILE, "w")
  if f then
    f:write("stop\n")
    f:close()
  elseif dict_task then
    dict_task:terminate()
  end
  if menubar then
    menubar:setTitle(" …")
    menubar:setTooltip("digivoice: transcribing and pasting…")
  end
  if banner then
    banner[2].text = "digivoice · pasting…"
  end
end

function M.toggle_dict()
  if dict_task and dict_task:isRunning() then
    stop_dict()
  else
    start_dict()
  end
end

-- Speaks the current selection only (digivoice speak --selection).
-- Soft-fails with a notify when nothing is selected. No clipboard/history fallback.
function M.speak_selection()
  local task = hs.task.new(DIGIVOICE, function(exitCode, stdOut, stdErr)
    if exitCode == 0 then
      local preview = (stdOut or ""):gsub("%s+$", "")
      notify("digivoice speak", preview ~= "" and preview or "spoken")
    else
      local err = (stdErr or ""):gsub("%s+$", "")
      if err == "" then
        err = "nothing selected — select text first"
      end
      notify("digivoice speak", err)
    end
  end, { "speak", "--selection" })
  if task then
    task:start()
  else
    notify("digivoice", "could not start digivoice speak")
  end
end

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
  notify(
    "digivoice",
    "hotkeys armed: Right Option = dict; double-tap Left Option = speak selection"
  )
end

function M.stop()
  tap:stop()
  if dict_task and dict_task:isRunning() then
    stop_dict()
  end
  hide_live_banner()
end

M.start()
return M
