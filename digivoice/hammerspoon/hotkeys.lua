--- Hotkey names from settings.json. No hs.* calls: tests load this file under plain Lua.
--- Defaults match the sample: Right Option, double-tap Left Option, Esc.
--- A string that does not parse is nil. The caller keeps the previous bind.

local M = {}

M.DEFAULTS = {
  dictation = "Right Option",
  speak = "Double-tap Left Option",
  cancel = "Esc",
}

-- ANSI keycodes (Mac). Modifier keys are phrases, not this table.
local KEYS = {
  a = 0, b = 11, c = 8, d = 2, e = 14, f = 3, g = 5, h = 4, i = 34, j = 38,
  k = 40, l = 37, m = 46, n = 45, o = 31, p = 35, q = 12, r = 15, s = 1, t = 17,
  u = 32, v = 9, w = 13, x = 7, y = 16, z = 6,
  ["0"] = 29, ["1"] = 18, ["2"] = 19, ["3"] = 20, ["4"] = 21,
  ["5"] = 23, ["6"] = 22, ["7"] = 26, ["8"] = 28, ["9"] = 25,
  space = 49, tab = 48, ["return"] = 36, enter = 36,
  esc = 53, escape = 53, delete = 51, backspace = 51,
  left = 123, right = 124, down = 125, up = 126,
}

local MODS = {
  ctrl = "ctrl", control = "ctrl",
  shift = "shift",
  alt = "alt", option = "alt", opt = "alt",
  cmd = "cmd", command = "cmd", super = "cmd", meta = "cmd",
}

local function trim(text)
  return (text:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function phrase(text)
  local lower = trim(text):lower():gsub("%s+", " ")
  return lower
end

local function spec(keycode, kind, ctrl, shift, alt, cmd, double)
  return {
    keycode = keycode,
    kind = kind,
    ctrl = ctrl,
    shift = shift,
    alt = alt,
    cmd = cmd,
    double = double,
  }
end

local function split_plus(text)
  local parts = {}
  local buf = ""
  for i = 1, #text do
    local ch = text:sub(i, i)
    if ch == "+" then
      local token = trim(buf)
      if token ~= "" then
        parts[#parts + 1] = token
      end
      buf = ""
    else
      buf = buf .. ch
    end
  end
  local token = trim(buf)
  if token ~= "" then
    parts[#parts + 1] = token
  end
  return parts
end

--- Parse one binding. Returns a spec, or nil when the text is not a key.
function M.parse_binding(text)
  if type(text) ~= "string" then
    return nil
  end
  local name = phrase(text)
  if name == "" then
    return nil
  end
  if name == "right option" or name == "right alt" then
    return spec(61, "flags", false, false, true, false, false)
  end
  if name == "left option" or name == "left alt" then
    return spec(58, "flags", false, false, true, false, false)
  end
  if name == "double-tap left option" or name == "double tap left option" then
    return spec(58, "flags", false, false, true, false, true)
  end
  if name == "esc" or name == "escape" then
    return spec(53, "key", false, false, false, false, false)
  end
  if name == "option" or name == "alt" or name == "opt" then
    return spec(61, "flags", false, false, true, false, false)
  end

  local parts = split_plus(name)
  if #parts == 0 then
    return nil
  end
  local ctrl, shift, alt, cmd, double = false, false, false, false, false
  local key = nil
  for _, token in ipairs(parts) do
    if token == "double-tap" or token == "doubletap" then
      double = true
    else
      local mod = MODS[token]
      if mod == "ctrl" then
        ctrl = true
      elseif mod == "shift" then
        shift = true
      elseif mod == "alt" then
        alt = true
      elseif mod == "cmd" then
        cmd = true
      elseif key == nil and KEYS[token] ~= nil then
        key = token
      else
        return nil
      end
    end
  end
  if key == nil then
    return nil
  end
  return spec(KEYS[key], "key", ctrl, shift, alt, cmd, double)
end

function M.defaults()
  local specs = {}
  for role, text in pairs(M.DEFAULTS) do
    local parsed = M.parse_binding(text)
    parsed.label = text
    specs[role] = parsed
  end
  return specs
end

--- Nested `hotkey_bindings` (real hs.json) or flat role strings (the test reader).
function M.bindings_from_settings(raw)
  if type(raw) ~= "table" then
    return nil
  end
  if type(raw.hotkey_bindings) == "table" then
    return raw.hotkey_bindings
  end
  local has_role = type(raw.dictation) == "string"
    or type(raw.speak) == "string"
    or type(raw.cancel) == "string"
  if has_role then
    return { dictation = raw.dictation, speak = raw.speak, cancel = raw.cancel }
  end
  return nil
end

--- Next specs plus warning strings. A bad or missing field keeps `previous[role]`.
function M.apply(previous, raw)
  previous = previous or M.defaults()
  raw = raw or {}
  local next_specs = {}
  local warnings = {}
  for _, role in ipairs({ "dictation", "speak", "cancel" }) do
    local text = raw[role]
    local kept = previous[role]
    if type(text) ~= "string" or trim(text) == "" then
      next_specs[role] = kept
    else
      local ok, parsed = pcall(M.parse_binding, text)
      if ok and type(parsed) == "table" then
        parsed.label = text
        next_specs[role] = parsed
      else
        next_specs[role] = kept
        local name = (kept and kept.label) or M.DEFAULTS[role]
        warnings[#warnings + 1] = role
          .. " binding '"
          .. text
          .. "' is not a key; keeping "
          .. name
      end
    end
  end
  return next_specs, warnings
end

function M.flags_match(spec, flags)
  flags = flags or {}
  return (flags.ctrl == true) == spec.ctrl
    and (flags.shift == true) == spec.shift
    and (flags.alt == true) == spec.alt
    and (flags.cmd == true) == spec.cmd
end

function M.matches(spec, keycode, flags)
  if type(spec) ~= "table" or spec.keycode ~= keycode then
    return false
  end
  return M.flags_match(spec, flags)
end

return M
