--- digivoice banner core: pure Lua, no Hammerspoon calls, so it can be unit-tested anywhere.
---
--- Holds everything the status banner decides:
---   * the square status-grid animations (a port of the digichat 5x5 grid states)
---   * which state to show (local phase vs the CLI's status.json)
---   * density (retract/full), text wrapping, box size, screen position
---   * banner settings from settings.json
---   * theme chrome (digichat light/dark flips; RYG status colors stay)
---   * drag/snap anchors, hover controls layout, reanchoring
--- init.lua only draws what this module computes. No chrome: no titles, no hints.
--- Dictated text is shown at once. Status labels stay off the banner; the grid is the state.

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

M.DENSITIES = {
  ["retract"] = true,
  ["full"] = true,
}

M.DEFAULTS = {
  live_banner = true,
  banner_position = "top-center",
  banner_density = "retract",
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

--- Click toggles retract → full → retract (no dedicated expand button).
function M.next_density(density)
  if density == "retract" then
    return "full"
  end
  return "retract"
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
  -- Retract auto-dismisses a few seconds after idle/done.
  return 4.0
end

--------------------------------------------------------------------------------
-- text, layout, position
--------------------------------------------------------------------------------

M.FONT_SIZE = 11
M.LINE_HEIGHT = 18
M.PAD = 10
M.ICON = 18
-- Full hugs content up to this width (no min-width gutter).
M.WIDTH_EXPANDED = 580
-- Full locks to the longest line, capped in characters.
M.FULL_MAX_CH = 47
M.LINES_EXPANDED = 14
M.MARGIN = 16
M.SNAP_PX = 36
M.CTRL_SIZE = 18
M.CTRL_GAP = 4
-- Conservative average glyph width so our wrapping is never re-wrapped by AppKit.
M.CHAR_WIDTH = M.FONT_SIZE * 0.6

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

--- Transcript only. Cancelled, empty, and error stay on the grid; no status
--- sentence sits beside the icon.
function M.body_for(view)
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

--- Pad every line to `width` with spaces so all lines share one uniform width.
function M.pad_lines(lines, width)
  local out = {}
  for i, line in ipairs(lines) do
    local pad = width - #line
    if pad > 0 then
      out[i] = line .. string.rep(" ", pad)
    else
      out[i] = line
    end
  end
  return out
end

--- Full density caps near half the viewport height (mock: max-height 50vh).
--- The budget is the box inside equal padding — no leftover header row.
function M.full_max_lines(screen_h)
  if type(screen_h) ~= "number" or screen_h <= 0 then
    return M.LINES_EXPANDED
  end
  return math.max(1, math.floor((screen_h * 0.5 - M.PAD * 2) / M.LINE_HEIGHT))
end

--- Vertical origin of the transcript so the first line's em-box centers on
--- the status-icon row. A one-line banner then reads as centered.
function M.text_origin_y()
  return M.PAD + (M.ICON - M.FONT_SIZE) / 2
end

--- Box geometry for a view at a density. No chrome: no title line, no hints —
--- state reads from the grid symbol/animation alone. Retract is the grid only.
--- Full widens and shows the whole transcript.
--- The box hugs content (no min-width gutter): width derives from the longest
--- wrapped line, capped at the full max. The width locks from the full
--- wrapped text up front.
--- Empty text hugs the grid. `raw` is the full transcript for copy.
function M.layout(view, kind, density, opts)
  kind = kind -- kind no longer changes geometry; kept for call shape.
  opts = opts or {}
  if density ~= "full" then
    density = "retract"
  end
  local text_x = M.PAD + M.ICON + 10
  local text_y = M.text_origin_y()
  local grid_side = M.PAD * 2 + M.ICON
  local function grid_only()
    return {
      w = grid_side,
      h = grid_side,
      text_x = text_x,
      text_y = text_y,
      text_w = 0,
      cols = 0,
      lines = {},
      body = "",
      clipped = false,
      total = 0,
      longest = 0,
      all = {},
      raw = "",
    }
  end
  local body = M.body_for(view)
  if density ~= "full" or body == "" then
    return grid_only()
  end
  local cols = math.min(math.floor((M.WIDTH_EXPANDED - text_x - M.PAD) / M.CHAR_WIDTH), M.FULL_MAX_CH)
  cols = math.max(8, cols)
  local all = M.wrap(body, cols)
  local longest = 0
  for _, line in ipairs(all) do
    longest = math.max(longest, #line)
  end
  longest = math.max(longest, 1)
  local limit = math.min(M.LINES_EXPANDED, M.full_max_lines(opts.screen_h))
  -- Full scrolls instead of truncating: plain window, no ellipsis mid-list.
  local padded = M.pad_lines(all, longest)
  local clipped = #padded > limit
  local lines = {}
  for i = 1, math.min(limit, #padded) do
    lines[i] = padded[i]
  end
  local width = text_x + longest * M.CHAR_WIDTH + M.PAD
  -- Text sits beside the grid. The box is the taller of the grid and the
  -- lines, plus the same PAD on every side. No header row under the text.
  local height = math.max(grid_side, M.PAD + #lines * M.LINE_HEIGHT + M.PAD)
  if type(opts.screen_h) == "number" and opts.screen_h > 0 then
    height = math.min(height, math.floor(opts.screen_h * 0.5))
  end
  return {
    w = width,
    h = height,
    text_x = text_x,
    text_y = text_y,
    text_w = width - text_x - M.PAD,
    cols = cols,
    lines = lines,
    body = table.concat(lines, "\n"),
    clipped = clipped,
    total = #all,
    longest = longest,
    all = M.pad_lines(all, longest),
    raw = body,
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

--- After a size change (density flip, hover controls), keep the pin so the
--- banner grows outward: center pins keep the center, left pins grow right,
--- right pins grow left, free floats keep their top-left (grid stays put).
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

--- Hover controls below the banner: icon-only copy + close, 18px squares.
--- Retract stacks them centered; full rows them right-aligned.
--- Frames are relative to the banner's top-left (y starts below the box).
function M.controls_layout(box_w, box_h, density)
  local y = box_h + M.CTRL_GAP
  if density ~= "full" then
    local x = (box_w - M.CTRL_SIZE) / 2
    return {
      dir = "stack",
      buttons = {
        { id = "copy", x = x, y = y, w = M.CTRL_SIZE, h = M.CTRL_SIZE },
        { id = "close", x = x, y = y + M.CTRL_SIZE + M.CTRL_GAP, w = M.CTRL_SIZE, h = M.CTRL_SIZE },
      },
    }
  end
  local total = M.CTRL_SIZE * 2 + M.CTRL_GAP
  local x = box_w - total
  return {
    dir = "row",
    buttons = {
      { id = "copy", x = x, y = y, w = M.CTRL_SIZE, h = M.CTRL_SIZE },
      { id = "close", x = x + M.CTRL_SIZE + M.CTRL_GAP, y = y, w = M.CTRL_SIZE, h = M.CTRL_SIZE },
    },
  }
end

--- Extra canvas height the hover controls need below the box.
function M.controls_height(density)
  if density ~= "full" then
    return M.CTRL_GAP + M.CTRL_SIZE * 2 + M.CTRL_GAP
  end
  return M.CTRL_GAP + M.CTRL_SIZE
end

return M
