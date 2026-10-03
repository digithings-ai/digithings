--- digivoice banner core: pure Lua, no Hammerspoon calls, so it can be unit-tested anywhere.
---
--- Holds everything the status banner decides:
---   * the square status-grid animations (a port of the digichat 5x5 grid states)
---   * which state to show (local phase vs the CLI's status.json)
---   * box size and screen position
---   * banner settings from settings.json
---   * theme chrome (digichat light/dark flips; RYG status colors stay)
---   * drag/snap anchors and reanchoring
--- init.lua only draws what this module computes. The surface is one status icon.
--- No status word, copy, close, pin button, transcript, or fact line.
--- Recording is a level meter on that same grid. The other marks stay and move.
--- The icon shows for recording, dictating, processing, a current error, or a
--- current warning. Pending, idle, and nothing-to-show hide it. banner_pinned
--- keeps the idle icon up. Density is ignored. banner_animations false holds
--- one frame.

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
  ["middle-left"] = true,
  ["middle-right"] = true,
  ["bottom-center"] = true,
  ["bottom-left"] = true,
  ["bottom-right"] = true,
  ["center"] = true,
}

M.DEFAULTS = {
  live_banner = true,
  banner_position = "top-center",
  banner_animations = true,
  banner_pinned = false,
}

function M.parse_settings(raw)
  local out = {
    live_banner = M.DEFAULTS.live_banner,
    banner_position = M.DEFAULTS.banner_position,
    banner_animations = M.DEFAULTS.banner_animations,
    banner_pinned = M.DEFAULTS.banner_pinned,
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
  if type(raw.banner_pinned) == "boolean" then
    out.banner_pinned = raw.banner_pinned
  end
  return out
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

local function glyph(dots)
  local set = {}
  for _, rc in ipairs(dots) do
    set[rc[1] * GRID + rc[2]] = true
  end
  return set
end

local CROSS =
  glyph({ { 0, 0 }, { 0, 4 }, { 1, 1 }, { 1, 3 }, { 2, 2 }, { 3, 1 }, { 3, 3 }, { 4, 0 }, { 4, 4 } })
local BANG = glyph({ { 0, 2 }, { 1, 2 }, { 2, 2 }, { 4, 2 } })
local STOP =
  glyph({ { 1, 1 }, { 1, 2 }, { 1, 3 }, { 2, 1 }, { 2, 2 }, { 2, 3 }, { 3, 1 }, { 3, 2 }, { 3, 3 } })

local RED = { red = 0.94, green = 0.27, blue = 0.27 }
local AMBER = { red = 0.96, green = 0.65, blue = 0.14 }
local INK = { red = 0.78, green = 0.80, blue = 0.82 }
local GRAY = { red = 0.62, green = 0.66, blue = 0.68 }
local DIM = 0.15

-- The marks stay on the grid. Recording is the level meter below.
local DICTATE = glyph({ { 1, 1 }, { 1, 3 }, { 2, 1 }, { 2, 2 }, { 2, 3 }, { 3, 1 }, { 3, 3 } })
-- Diamond, clockwise from the top, so a highlight can chase the outline.
local RING_RC = {
  { 0, 2 },
  { 1, 3 },
  { 2, 4 },
  { 3, 3 },
  { 4, 2 },
  { 3, 1 },
  { 2, 0 },
  { 1, 1 },
}
local PROCESS = glyph(RING_RC)
local RING = {}
local RING_AT = {}
for n, rc in ipairs(RING_RC) do
  local cell = rc[1] * GRID + rc[2]
  RING[n] = cell
  RING_AT[cell] = n - 1
end

local function clamp01(x)
  if x < 0 then
    return 0
  end
  if x > 1 then
    return 1
  end
  return x
end

-- Stable 0..1 mix. Columns do not share a phase, and tests can replay a frame.
local function hash01(n)
  local x = (n * 1103515245 + 12345) % 2147483648
  return x / 2147483648
end

--- Turn a clock into 0..1. Wall-clock seconds are ~1e9; sin of that raw angle
--- sticks on some libm builds, which froze the recording meter.
local function cycle(t, period, phase)
  return ((t / period) + (phase or 0)) % 1
end

local function wave(turns)
  return 0.5 + 0.5 * math.sin(turns * (2 * math.pi))
end

local function meter_level(col, t)
  local period_a = 0.42 + hash01(col * 17 + 3) * 0.36
  local period_b = 0.28 + hash01(col * 29 + 11) * 0.22
  local wobble = wave(cycle(t, period_a, hash01(col * 13 + 5)))
  local flutter = wave(cycle(t, period_b, hash01(col * 19 + 7)))
  local flow = wave(cycle(t, 1.35, -col * 0.22))
  return clamp01(0.08 + 0.92 * (0.46 * wobble + 0.24 * flutter + 0.30 * flow))
end

-- Row 0 is the top of the icon. A bar fills upward from row 4.
local function meter_alpha(row, col, t)
  local covered = meter_level(col, t) * GRID - (GRID - 1 - row)
  if covered >= 1 then
    return 1
  end
  if covered <= 0 then
    return 0.10
  end
  return 0.10 + 0.90 * covered
end

local function sweep_glyph(mark, i, col, t, period)
  if not mark[i] then
    return DIM
  end
  -- Stay on the mark (columns 1..3) so the band never parks off to the side.
  local pos = 1 + cycle(t, period, 0) * 2
  local d = math.abs(col - pos)
  local peak = math.exp(-(d * d) / 0.42)
  return 0.32 + 0.68 * peak
end

local function chase(i, t, period)
  local idx = RING_AT[i]
  if idx == nil then
    return DIM
  end
  local n = #RING
  local head = cycle(t, period, 0) * n
  local dist = math.abs(idx - head)
  if dist > n / 2 then
    dist = n - dist
  end
  local peak = math.max(0, 1 - dist / 1.65)
  return 0.34 + 0.66 * peak
end

local function ripple_glyph(mark, i, row, col, t, period)
  if not mark[i] then
    return DIM
  end
  local dist = math.max(math.abs(row - 2), math.abs(col - 2))
  local x = cycle(t, period, -dist * 0.18)
  local f = 0.5 * (1 + math.cos(2 * math.pi * x))
  return 0.30 + 0.70 * f
end

local function warn_motion(i, row, _, t)
  if not BANG[i] then
    return DIM
  end
  local turn = cycle(t, 1.15, 0)
  if row == 4 then
    local f = 0
    if turn >= 0.58 then
      local u = (turn - 0.58) / 0.42
      f = math.sin(math.pi * math.min(1, u))
    end
    return 0.25 + 0.75 * f
  end
  local head = 2
  if turn < 0.58 then
    head = (turn / 0.58) * 2
  end
  local d = math.abs(row - head)
  local peak = math.max(0, 1 - d / 1.05)
  return 0.34 + 0.66 * peak
end

local function idle_motion(i, row, col, t)
  if not STOP[i] then
    return DIM
  end
  local dist = math.abs(row - 2) + math.abs(col - 2)
  local x = cycle(t, 2.6, -dist * 0.07)
  local f = 0.5 * (1 + math.cos(2 * math.pi * x))
  return 0.20 + 0.42 * f
end

local MATRIX = {
  record = {
    color = RED,
    meter = true,
    motion = function(_, row, col, t)
      return meter_alpha(row, col, t)
    end,
  },
  dictate = {
    color = INK,
    glyph = DICTATE,
    motion = function(i, _, col, t)
      return sweep_glyph(DICTATE, i, col, t, 0.9)
    end,
  },
  process = {
    color = INK,
    glyph = PROCESS,
    motion = function(i, _, _, t)
      return chase(i, t, 1.15)
    end,
  },
  error = {
    color = RED,
    glyph = CROSS,
    motion = function(i, row, col, t)
      return ripple_glyph(CROSS, i, row, col, t, 1.05)
    end,
  },
  warn = {
    color = AMBER,
    glyph = BANG,
    motion = function(i, row, col, t)
      return warn_motion(i, row, col, t)
    end,
  },
  idle = {
    color = GRAY,
    glyph = STOP,
    base = 0.35,
    motion = function(i, row, col, t)
      return idle_motion(i, row, col, t)
    end,
  },
}

M.MATRIX = MATRIX

-- Existing pipeline states only. Dictating is the transcribe step after capture.
M.STATE_MATRIX = {
  loading = "process",
  recording = "record",
  transcribing = "dictate",
  rewriting = "process",
  pasting = "process",
  speaking = "process",
  done = "idle",
  cancelled = "idle",
  cancelling = "idle",
  empty = "idle",
  pending = "idle",
  warning = "warn",
  error = "error",
  idle = "idle",
}

--- Names drawn as icons. Idle is the calm mark for an always-visible banner.
M.ICON_PHASE = {
  recording = "recording",
  transcribing = "dictating",
  loading = "processing",
  rewriting = "processing",
  pasting = "processing",
  speaking = "processing",
  error = "error",
  warning = "warning",
  empty = "",
  pending = "",
  idle = "idle",
  done = "idle",
  cancelled = "idle",
  cancelling = "idle",
}

local ALWAYS_SHOW = {
  recording = true,
  dictating = true,
  processing = true,
  error = true,
  warning = true,
}

function M.icon_phase(state)
  return M.ICON_PHASE[state] or ""
end

--- Recording, dictating, processing, and a current error or warning draw.
--- Pending, idle, empty, and a finished take hide. Pin keeps the idle icon.
function M.should_draw(state, pinned, pending)
  if pending == true or state == "pending" or state == "empty" then
    return false
  end
  local phase = M.icon_phase(state)
  if ALWAYS_SHOW[phase] then
    return true
  end
  if phase == "idle" then
    return pinned == true
  end
  return false
end

--- One rule for every banner path. `pending` hides even a pinned idle icon.
local PATH_STATE = {
  launch = "idle",
  pin_on = "idle",
  pin_off = "idle",
  show = "recording",
  hide = "idle",
  toggle = "recording",
  take_start = "pending",
  recording = "recording",
  transcribing = "transcribing",
  loading = "loading",
  rewriting = "rewriting",
  pasting = "pasting",
  speaking = "speaking",
  empty = "empty",
  error = "error",
  warning = "warning",
  take_end = "done",
  pending = "pending",
}

function M.route_banner(path, opts)
  opts = opts or {}
  if path == "hide" then
    return false
  end
  if path == "toggle" and opts.showing == true then
    return false
  end
  local pinned = opts.pinned == true
  if path == "pin_on" then
    pinned = true
  elseif path == "pin_off" then
    pinned = false
  end
  local pending = opts.pending == true or path == "pending" or path == "take_start"
  if path == "show" or path == "toggle" then
    pending = opts.pending == true
  end
  return M.should_draw(PATH_STATE[path] or path, pinned, pending)
end

--- Click focuses a digivoice terminal that is already open, otherwise opens one.
function M.focus_action(already_open)
  if already_open then
    return "focus"
  end
  return "open"
end

--- A pid file with one integer means the terminal UI is already up.
function M.tui_is_open(pid_text)
  if type(pid_text) ~= "string" then
    return false
  end
  return pid_text:match("^%s*%d+%s*$") ~= nil
end

function M.matrix_for(state)
  return MATRIX[M.STATE_MATRIX[state] or "load"]
end

local function glyph_alpha(cfg, i)
  local on = (cfg.glyph == nil) or (cfg.glyph[i] == true)
  if on then
    return cfg.base or 1
  end
  return cfg.dim or DIM
end

--- Opacity of cell `i` (0-based, row-major) at time `t` seconds.
--- Animations off holds one frame: the meter at t = 0, or the full mark.
function M.dot_alpha(state, i, t, animate)
  local cfg = M.matrix_for(state)
  if type(cfg) ~= "table" then
    return 0
  end
  local row, col = i // GRID, i % GRID
  if not animate then
    if cfg.meter then
      return meter_alpha(row, col, 0)
    end
    return glyph_alpha(cfg, i)
  end
  if cfg.motion then
    return cfg.motion(i, row, col, t or 0)
  end
  return glyph_alpha(cfg, i)
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

function M.linger_seconds(state, pinned)
  -- banner_pinned is the always-on mode. There is no full-vs-retract density.
  local phase = M.icon_phase(state)
  if pinned and (phase == "error" or phase == "warning" or phase == "idle") then
    if state == "done" or state == "cancelled" or state == "cancelling" then
      return 1.2
    end
    return nil
  end
  if pinned and (phase == "recording" or phase == "dictating" or phase == "processing") then
    return nil
  end
  if pinned then
    return nil
  end
  -- Retract: a finished take is not a current update. Error and warning linger
  -- only while they are still the thing to show.
  if state == "done" or state == "cancelled" or state == "cancelling" or state == "idle" then
    return 0
  end
  if state == "error" or state == "warning" then
    return 4.0
  end
  if state == "empty" or state == "pending" then
    return 0
  end
  return nil
end

--------------------------------------------------------------------------------
-- layout, position
--------------------------------------------------------------------------------

M.PAD = 10
M.ICON = 18
M.MARGIN = 16
M.SNAP_PX = 36

--- DigiChat light/dark flips. Status (RYG) colors stay; only chrome flips.
--- Dark ground is the digiquant remock canvas (docs/dashboard-mocks/canvas/mock.css
--- on the remock branch): --bg #000, --ink #ededed, --hair white at 0.16.
--- That sheet is dark-only. Light ground is the paired ivory paper for
--- digithings.ai / digiquant in packages/design/spec/index.html
--- (--paper #F9F8F6, --paper-ink #141413, --paper-hair #E8E6DC).
--- Neither pair is the live tokens.css canvas (#0A0E0C / #FBFBF9).
M.CHROME = {
  dark = {
    bg = { red = 0, green = 0, blue = 0, alpha = 1 },
    text = { red = 0xED / 255, green = 0xED / 255, blue = 0xED / 255, alpha = 1 },
    border = { red = 1, green = 1, blue = 1, alpha = 0.16 },
  },
  light = {
    bg = { red = 0xF9 / 255, green = 0xF8 / 255, blue = 0xF6 / 255, alpha = 1 },
    text = { red = 0x14 / 255, green = 0x14 / 255, blue = 0x13 / 255, alpha = 1 },
    border = { red = 0xE8 / 255, green = 0xE6 / 255, blue = 0xDC / 255, alpha = 1 },
  },
}

function M.theme_colors(theme)
  if theme == "light" then
    return M.CHROME.light
  end
  return M.CHROME.dark
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

--- Square icon only. Transcript length and a leftover density do not change the box.
function M.layout(view)
  local state = ""
  if type(view) == "table" then
    state = view.state or ""
  end
  local grid_side = M.PAD * 2 + M.ICON
  return {
    w = grid_side,
    h = grid_side,
    lines = {},
    body = "",
    phase = M.icon_phase(state),
    clipped = false,
    raw = "",
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
    -- center, middle-left, middle-right: vertically centered.
    y = frame.y + (frame.h - size.h) / 2
  end
  return { x = x, y = y }
end

--- Anchor id (tl|tc|tr|ml|c|mr|bl|bc|br) for a banner_position setting.
function M.anchor_for_position(position)
  local map = {
    ["top-left"] = "tl",
    ["top-center"] = "tc",
    ["top-right"] = "tr",
    ["middle-left"] = "ml",
    ["center"] = "c",
    ["middle-right"] = "mr",
    ["bottom-left"] = "bl",
    ["bottom-center"] = "bc",
    ["bottom-right"] = "br",
  }
  return map[position] or "tc"
end
--- Ids: tl | tc | tr | ml | c | mr | bl | bc | br.
function M.anchors(frame, size, margin)
  margin = margin or M.MARGIN
  local min_x, min_y = frame.x + margin, frame.y + margin
  local max_x = math.max(min_x, frame.x + frame.w - size.w - margin)
  local max_y = math.max(min_y, frame.y + frame.h - size.h - margin)
  local mid_x, mid_y = (min_x + max_x) / 2, (min_y + max_y) / 2
  return {
    { id = "tl", x = min_x, y = min_y },
    { id = "tc", x = mid_x, y = min_y },
    { id = "tr", x = max_x, y = min_y },
    { id = "ml", x = min_x, y = mid_y },
    { id = "c", x = mid_x, y = mid_y },
    { id = "mr", x = max_x, y = mid_y },
    { id = "bl", x = min_x, y = max_y },
    { id = "bc", x = mid_x, y = max_y },
    { id = "br", x = max_x, y = max_y },
  }
end

--- Clamp a free position inside the screen with the edge margin kept.
function M.clamp_position(x, y, frame, size, margin)
  margin = margin or M.MARGIN
  local max_x = math.max(frame.x + margin, frame.x + frame.w - size.w - margin)
  local max_y = math.max(frame.y + margin, frame.y + frame.h - size.h - margin)
  return {
    x = math.min(max_x, math.max(frame.x + margin, x)),
    y = math.min(max_y, math.max(frame.y + margin, y)),
  }
end

--- Snap a free position to the nearest anchor within `threshold` px.
--- Returns {x, y, anchor} where anchor is nil when nothing is near.
function M.snap_position(x, y, frame, size, margin, threshold)
  threshold = threshold or M.SNAP_PX
  local best, best_d
  for _, a in ipairs(M.anchors(frame, size, margin)) do
    local d = math.sqrt((x - a.x) * (x - a.x) + (y - a.y) * (y - a.y))
    if best_d == nil or d < best_d then
      best, best_d = a, d
    end
  end
  if best ~= nil and best_d <= threshold then
    return { x = best.x, y = best.y, anchor = best.id }
  end
  local clamped = M.clamp_position(x, y, frame, size, margin)
  return { x = clamped.x, y = clamped.y, anchor = nil }
end

--- Resolve a persisted {x, y, anchor} position: clamp it onto the current
--- screen. Returns nil when there is nothing persisted worth keeping.
function M.resolve_saved(saved, frame, size, margin)
  if type(saved) ~= "table" or type(saved.x) ~= "number" or type(saved.y) ~= "number" then
    return nil
  end
  local clamped = M.clamp_position(saved.x, saved.y, frame, size, margin)
  return { x = clamped.x, y = clamped.y, anchor = saved.anchor }
end

--- Keep the anchor when the box size changes: center stays centered, left grows
--- right, right grows left, and a free float keeps its top-left.
function M.reanchor(prev, size, anchor)
  anchor = anchor or "free"
  local cx, cy = prev.x + prev.w / 2, prev.y + prev.h / 2
  if anchor == "c" or anchor == "tc" or anchor == "bc" then
    if anchor == "tc" then
      return { x = cx - size.w / 2, y = prev.y }
    elseif anchor == "bc" then
      return { x = cx - size.w / 2, y = prev.y + prev.h - size.h }
    end
    return { x = cx - size.w / 2, y = cy - size.h / 2 }
  elseif anchor == "tl" or anchor == "ml" or anchor == "bl" then
    local y = prev.y
    if anchor == "ml" then
      y = cy - size.h / 2
    elseif anchor == "bl" then
      y = prev.y + prev.h - size.h
    end
    return { x = prev.x, y = y }
  elseif anchor == "tr" or anchor == "mr" or anchor == "br" then
    local y = prev.y
    if anchor == "mr" then
      y = cy - size.h / 2
    elseif anchor == "br" then
      y = prev.y + prev.h - size.h
    end
    return { x = prev.x + prev.w - size.w, y = y }
  end
  return { x = prev.x, y = prev.y }
end

return M
