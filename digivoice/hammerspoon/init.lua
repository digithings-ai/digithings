--- digivoice Hammerspoon sample adapter
--- Locked binds (do not invent others):
---   Right Option          → dict toggle (press start / press stop → transcribe + paste)
---   Ctrl+Shift+Option     → speak (clipboard, else last history)
---
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

local DIGIVOICE = digivoice_bin()
local STOP_FILE = data_dir() .. "/dict.stop"
local dict_task = nil

local function notify(title, text)
  hs.notify.new({ title = title, informativeText = text or "" }):send()
end

local function start_dict()
  hs.fs.mkdir(data_dir())
  os.remove(STOP_FILE)
  dict_task = hs.task.new(DIGIVOICE, function(exitCode, stdOut, stdErr)
    dict_task = nil
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
    notify("digivoice", "could not start digivoice dict")
    return
  end
  dict_task:start()
  notify("digivoice", "recording… (Right Option again to stop)")
end

local function stop_dict()
  -- Touch the stop-file so digivoice ends sox/ffmpeg cleanly, then
  -- transcribes + pastes. Prefer stop-file over killing the process.
  local f = io.open(STOP_FILE, "w")
  if f then
    f:write("stop\n")
    f:close()
  elseif dict_task then
    dict_task:terminate()
  end
end

function M.toggle_dict()
  if dict_task and dict_task:isRunning() then
    stop_dict()
  else
    start_dict()
  end
end

function M.speak_clipboard_or_history()
  local task = hs.task.new(DIGIVOICE, function(exitCode, stdOut, stdErr)
    if exitCode == 0 then
      notify("digivoice speak", ((stdOut or ""):gsub("%s+$", "")))
    else
      notify("digivoice speak failed", ((stdErr or ""):gsub("%s+$", "")))
    end
  end, { "speak", "--clipboard-or-history" })
  if task then
    task:start()
  else
    notify("digivoice", "could not start digivoice speak")
  end
end

-- Right Option keycode is 61; Left Option is 58 (ignored).
local RIGHT_OPTION = 61
local right_option_down = false
local speak_chord_latched = false

local tap = hs.eventtap.new({ hs.eventtap.event.types.flagsChanged }, function(event)
  local flags = event:getFlags()
  local ctrl = flags.ctrl == true
  local shift = flags.shift == true
  local alt = flags.alt == true
  local keyCode = event:getKeyCode()

  -- Ctrl+Shift+Option → speak once per chord press (any Option key).
  local speak_chord = ctrl and shift and alt
  if speak_chord and not speak_chord_latched then
    speak_chord_latched = true
    M.speak_clipboard_or_history()
    return false
  end
  if not speak_chord then
    speak_chord_latched = false
  end

  -- Right Option alone → dict toggle on press. Skip when ctrl/shift held
  -- so the speak chord never also starts a recording.
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
  notify("digivoice", "hotkeys armed: Right Option = dict; Ctrl+Shift+Option = speak")
end

function M.stop()
  tap:stop()
  if dict_task and dict_task:isRunning() then
    stop_dict()
  end
end

M.start()
return M
