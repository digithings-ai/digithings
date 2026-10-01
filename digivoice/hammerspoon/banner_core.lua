--- digivoice banner core: pure Lua, no Hammerspoon calls, so it can be unit-tested anywhere.
---
--- Holds everything the status banner decides:
---   * the square status-grid animations (a port of the digichat 5x5 grid states)
---   * which state to show (local phase vs the CLI's status.json)
---   * density (mini/peek/full), text wrapping/clipping, box size, screen position
---   * banner settings from settings.json
--- init.lua only draws what this module computes. No chrome: no titles, no hints.

local M = {}

M.GRID = 5
M.ESC_KEYCODE = 53

-- Ship model: no launch toast / menubar. COMMANDS stays for docs and doctor text.
M.COMMANDS = {
  "Right Option = dictate (press again to stop)",
  "Esc = cancel the take",
  "double-tap Left Option = speak selection",
}

M.POSITIONS = {
  ["top-center"] = true,
  ["top-left"] = true,
  ["top-right"] = true,
  ["bottom-center"] = true,
  ["bottom-left"] = true,
  ["bottom-right"] = true,
  ["center"] = true,
}

M.DENSITIES = {
  ["mini"] = true,
  ["peek"] = true,
  ["full"] = true,
}

M.DEFAULTS = {
  live_banner = true,
  banner_position = "top-center",
  banner_density = "peek",
  banner_animations = true,
}

function M.parse_settings(raw)
  local out = {
    live_banner = M.DEFAULTS.live_banner,
    banner_position = M.DEFAULTS.banner_position,
    banner_density = M.DEFAULTS.banner_density,
    banner_animations = M.DEFAULTS.banner_animations,
  }
  if type(raw) ~= "table" then
    return out
  end
  if type(raw.live_banner) == "boolean" then
    out.live_banner = raw.live_banner
  end
  if type(raw.banner_animations) == "boolean" then
    out.banner_animations = raw.banner_animations
  end
  if type(raw.banner_position) == "string" and M.POSITIONS[raw.banner_position] then
    out.banner_position = raw.banner_position
  end
  if type(raw.banner_density) == "string" and M.DENSITIES[raw.banner_density] then
    out.banner_density = raw.banner_density
  end
  return out
end

--- Click cycles density mini → peek → full → mini (no dedicated expand button).
function M.next_density(density)
  if density == "mini" then
    return "peek"
  elseif density == "peek" then
    return "full"
  end
  return "mini"
end

function M.launch_notice(bin)
  local lines = { "commands: " .. table.concat(M.COMMANDS, "; ") }
  if bin and bin ~= "" then
    lines[#lines + 1] = "cli: " .. bin
  end
  return table.concat(lines, "\n")
end

function M.is_cancel_key(keycode, flags)
  if keycode ~= M.ESC_KEYCODE then
    return false
  end
  flags = flags or {}
  return not (flags.cmd or flags.ctrl or flags.alt or flags.shift)
end

--------------------------------------------------------------------------------
-- dot matrix (port of packages/ui .../dot-matrix.tsx)
--------------------------------------------------------------------------------

local GRID = M.GRID
local CENTER = (GRID - 1) / 2

-- Deterministic bit-mixing hash, same as the TSX original. Returns seconds.
local function hash(n, salt, range)
  local h = ((n * 374761393) + (salt * 668265263)) & 0xFFFFFFFF
  h = ((h ~ (h >> 13)) * 1274126177) & 0xFFFFFFFF
  return ((h ~ (h >> 16)) % range) / 1000
end

local function glyph(dots)
  local set = {}
  for _, rc in ipairs(dots) do
    set[rc[1] * GRID + rc[2]] = true
  end
  return set
end

local CHECK = glyph({ { 1, 4 }, { 2, 3 }, { 3, 0 }, { 3, 2 }, { 4, 1 } })
local CROSS =
  glyph({ { 0, 0 }, { 0, 4 }, { 1, 1 }, { 1, 3 }, { 2, 2 }, { 3, 1 }, { 3, 3 }, { 4, 0 }, { 4, 4 } })
local BANG = glyph({ { 0, 2 }, { 1, 2 }, { 2, 2 }, { 4, 2 } })
local STOP =
  glyph({ { 1, 1 }, { 1, 2 }, { 1, 3 }, { 2, 1 }, { 2, 2 }, { 2, 3 }, { 3, 1 }, { 3, 2 }, { 3, 3 } })

local TEAL = { red = 0.08, green = 0.72, blue = 0.65 }
local RED = { red = 0.94, green = 0.27, blue = 0.27 }
local GREEN = { red = 0.20, green = 0.78, blue = 0.45 }
local AMBER = { red = 0.96, green = 0.65, blue = 0.14 }
local GRAY = { red = 0.62, green = 0.66, blue = 0.68 }

-- Matrix states. `wave` = recording, `speak`, `load` family = everything in flight.
local MATRIX = {
  load = {
    color = TEAL,
    blink = function(i)
      return { duration = 0.9 + hash(i, 2, 700), delay = -hash(i, 1, 1200), lo = 0.15 }
    end,
  },
  think = {
    color = TEAL,
    blink = function(_, row, col)
      return { duration = 1.2, delay = -(row + col) * 0.09, lo = 0.2 }
    end,
  },
  sync = {
    color = TEAL,
    blink = function(_, row, col)
      local turn = (math.atan(row - CENTER, col - CENTER) + math.pi) / (2 * math.pi)
      return { duration = 1.3, delay = -turn * 1.3, lo = 0.2 }
    end,
  },
  paste = {
    color = TEAL,
    blink = function(_, row)
      return { duration = 1, delay = -row * 0.12, lo = 0.2 }
    end,
  },
  wave = {
    color = RED,
    blink = function(_, _, col)
      return { duration = 0.7 + hash(col, 4, 500), delay = -hash(col, 5, 900), lo = 0.25 }
    end,
  },
  speak = {
    color = TEAL,
    blink = function(_, _, col)
      return { duration = 0.4 + hash(col, 6, 350), delay = -hash(col, 7, 700), lo = 0.2 }
    end,
  },
  success = { color = GREEN, glyph = CHECK },
  error = {
    color = RED,
    glyph = CROSS,
    blink = function()
      return { duration = 1.1, delay = 0, lo = 0.4 }
    end,
  },
  warn = {
    color = AMBER,
    glyph = BANG,
    blink = function()
      return { duration = 1.6, delay = 0, lo = 0.45 }
    end,
  },
  stopped = { color = GRAY, glyph = STOP },
}

M.MATRIX = MATRIX

-- Banner state -> matrix state.
M.STATE_MATRIX = {
  loading = "load",
  recording = "wave",
  transcribing = "think",
  rewriting = "sync",
  pasting = "paste",
  speaking = "speak",
  done = "success",
  cancelled = "stopped",
  cancelling = "stopped",
  empty = "warn",
  error = "error",
}

M.LABELS = {
  loading = "loading",
  recording = "recording",
  transcribing = "transcribing",
  rewriting = "rewriting",
  pasting = "pasting",
  speaking = "speaking",
  done = "done",
  cancelled = "cancelled",
  cancelling = "cancelling",
  empty = "nothing heard",
  error = "error",
}

function M.matrix_for(state)
  return MATRIX[M.STATE_MATRIX[state] or "load"]
end

--- Opacity of dot `i` (0-based, row-major) at time `t` seconds.
--- With animations off the same function is frozen at t = 0 (a still frame).
function M.dot_alpha(state, i, t, animate)
  local cfg = M.matrix_for(state)
  local row, col = i // GRID, i % GRID
  local on = (cfg.glyph == nil) or (cfg.glyph[i] == true)
  local hi = on and (cfg.base or 1) or (cfg.dim or 0.15)
  local blink = on and cfg.blink and cfg.blink(i, row, col) or nil
  if not blink then
    return hi
  end
  local now = animate and t or 0
  local x = ((now - blink.delay) / blink.duration) % 1
  local f = 0.5 * (1 + math.cos(2 * math.pi * x))
  return blink.lo + (hi - blink.lo) * f
end

--------------------------------------------------------------------------------
-- which state to show
--------------------------------------------------------------------------------

local RANK = {
  loading = 0,
  recording = 1,
  speaking = 1,
  transcribing = 2,
  rewriting = 3,
  pasting = 4,
  done = 5,
  cancelled = 5,
  empty = 5,
  error = 5,
  cancelling = 6,
}

local CANCELLABLE = { loading = true, recording = true, transcribing = true, rewriting = true }

--- Esc cancels a dictation until it reaches paste. Speech is never Esc-cancelled.
function M.cancellable(kind, state)
  return kind == "dict" and CANCELLABLE[state] == true
end

--- A snapshot counts only when it belongs to this session: same kind, written
--- after the session started (status.json outlives the process that wrote it).
function M.snapshot_valid(snapshot, session)
  return type(snapshot) == "table"
    and snapshot.kind == session.kind
    and type(snapshot.updated_ms) == "number"
    and snapshot.updated_ms >= session.start_ms
    and RANK[snapshot.state] ~= nil
end

--- Merge the adapter's own phase with the CLI's snapshot: the later stage wins,
--- ties go to the snapshot because it carries the text.
function M.pick_view(local_state, snapshot, session)
  local view = { state = local_state, text = "", detail = "" }
  if M.snapshot_valid(snapshot, session) then
    if (RANK[snapshot.state] or 0) >= (RANK[local_state] or 0) then
      view.state = snapshot.state
      view.text = snapshot.text or ""
      view.detail = snapshot.detail or ""
    end
  end
  return view
end

local function last_line(text)
  local found = ""
  for line in tostring(text or ""):gmatch("[^\r\n]+") do
    if line:match("%S") then
      found = line
    end
  end
  return (found:gsub("^%s+", ""):gsub("%s+$", ""):gsub("^digivoice[%w ]*:%s*", ""))
end

M.last_line = last_line

--- View once the CLI process has exited. Exit 3 = cancelled; 0 = done; else error
--- (or "nothing heard" when the CLI said the take was empty).
function M.final_view(code, snapshot, session, stdout, stderr, cancelling)
  local valid = M.snapshot_valid(snapshot, session)
  if code == 3 then
    return { state = "cancelled", text = "", detail = "" }
  end
  if code == 0 then
    local text = valid and snapshot.text or ""
    if text == "" then
      text = (tostring(stdout or ""):gsub("%s+$", ""))
    end
    return { state = "done", text = text, detail = valid and snapshot.detail or "" }
  end
  if cancelling then
    return { state = "cancelled", text = "", detail = "" }
  end
  if valid and snapshot.state == "empty" then
    return { state = "empty", text = "", detail = snapshot.detail or "" }
  end
  local detail = last_line(stderr)
  if detail == "" and valid then
    detail = snapshot.detail or ""
  end
  if detail == "" then
    detail = "exit " .. tostring(code)
  end
  return { state = "error", text = "", detail = detail }
end

function M.linger_seconds(state, density)
  -- Full density stays until collapsed or removed: no auto-hide timer.
  if density == "full" then
    return nil
  end
  if state == "error" then
    return 4.0
  elseif state == "empty" then
    return 2.0
  elseif state == "cancelled" then
    return 1.2
  end
  -- Peek (and mini) auto-dismiss a few seconds after idle/done.
  return 4.0
end

--------------------------------------------------------------------------------
-- text, layout, position
--------------------------------------------------------------------------------

M.FONT_SIZE = 13
M.LINE_HEIGHT = 17
M.PAD = 12
M.ICON = 28
M.HEAD_HEIGHT = 28
M.WIDTH_COLLAPSED = 380
M.WIDTH_EXPANDED = 580
M.LINES_COLLAPSED = 3
M.LINES_EXPANDED = 14
M.MARGIN = 12
-- Conservative average glyph width so our wrapping is never re-wrapped by AppKit.
M.CHAR_WIDTH = M.FONT_SIZE * 0.6

function M.body_for(view)
  if view.state == "error" then
    return view.detail ~= "" and view.detail or "see the Hammerspoon console"
  elseif view.state == "cancelled" or view.state == "cancelling" then
    return "take discarded; nothing pasted or saved"
  elseif view.state == "empty" then
    return "no speech detected; nothing pasted"
  end
  return view.text or ""
end

--- Greedy word wrap to `cols` columns. Hard-splits words longer than a line.
function M.wrap(text, cols)
  local lines = {}
  cols = math.max(8, cols)
  for paragraph in (tostring(text or "") .. "\n"):gmatch("(.-)\r?\n") do
    local line = ""
    for w in paragraph:gmatch("%S+") do
      local word = w
      while #word > cols do
        if line ~= "" then
          lines[#lines + 1] = line
          line = ""
        end
        lines[#lines + 1] = word:sub(1, cols)
        word = word:sub(cols + 1)
      end
      if line == "" then
        line = word
      elseif #line + 1 + #word <= cols then
        line = line .. " " .. word
      else
        lines[#lines + 1] = line
        line = word
      end
    end
    if line ~= "" then
      lines[#lines + 1] = line
    end
  end
  return lines
end

--- Keep `max` lines; the last kept line ends in an ellipsis when text was cut.
function M.clip_lines(lines, max, cols)
  if #lines <= max then
    return lines, false
  end
  local out = {}
  for i = 1, max do
    out[i] = lines[i]
  end
  local last = out[max]
  if #last > cols - 1 then
    last = last:sub(1, cols - 1)
  end
  out[max] = (last:gsub("%s+$", "")) .. "…"
  return out, true
end

--- Square frame for status-grid cell `i` (0-based, row-major): DigiChat-style
--- squares, not dots. The grid hugs the top-left with equal padding.
function M.cell_box(i)
  local pitch = M.ICON / M.GRID
  local side = pitch * 0.66
  local row, col = i // GRID, i % GRID
  local cx = M.PAD + pitch * (col + 0.5)
  local cy = M.PAD + pitch * (row + 0.5)
  return { x = cx - side / 2, y = cy - side / 2, w = side, h = side }
end

--- Box geometry for a view at a density. No chrome: no title line, no hints —
--- state reads from the grid symbol/animation alone. Mini is grid only.
--- Peek is a short glimpse; full widens and shows the whole transcript.
function M.layout(view, kind, density)
  kind = kind -- kind no longer changes geometry; kept for call shape.
  if density ~= "peek" and density ~= "full" then
    density = "mini"
  end
  local text_x = M.PAD + M.ICON + 10
  local function columns(width)
    return math.floor((width - text_x - M.PAD) / M.CHAR_WIDTH)
  end
  if density == "mini" then
    local side = M.PAD * 2 + M.ICON
    return {
      w = side,
      h = side,
      text_x = text_x,
      text_w = 0,
      cols = 0,
      lines = {},
      body = "",
      clipped = false,
    }
  end
  local body = M.body_for(view)
  local width = density == "full" and M.WIDTH_EXPANDED or M.WIDTH_COLLAPSED
  local cols = columns(width)
  local limit = density == "full" and M.LINES_EXPANDED or M.LINES_COLLAPSED
  local lines, clipped = M.clip_lines(M.wrap(body, cols), limit, cols)
  local height = M.PAD * 2 + M.ICON
  if #lines > 0 then
    height = math.max(height, M.PAD + M.HEAD_HEIGHT + #lines * M.LINE_HEIGHT + M.PAD)
  end
  return {
    w = width,
    h = height,
    text_x = text_x,
    text_w = width - text_x - M.PAD,
    cols = cols,
    lines = lines,
    body = table.concat(lines, "\n"),
    clipped = clipped,
  }
end

--- Top-left corner of a box of `size` inside screen `frame` for a position name.
function M.resolve_position(position, frame, size, margin)
  margin = margin or M.MARGIN
  local x, y
  if position:find("left", 1, true) then
    x = frame.x + margin
  elseif position:find("right", 1, true) then
    x = frame.x + frame.w - size.w - margin
  else
    x = frame.x + (frame.w - size.w) / 2
  end
  if position:find("top", 1, true) then
    y = frame.y + margin
  elseif position:find("bottom", 1, true) then
    y = frame.y + frame.h - size.h - margin
  else
    y = frame.y + (frame.h - size.h) / 2
  end
  return { x = x, y = y }
end

return M
