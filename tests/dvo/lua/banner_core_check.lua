-- Pure-logic checks for digivoice/hammerspoon/banner_core.lua. Env: ADAPTER_DIR.
local core = dofile(os.getenv("ADAPTER_DIR") .. "/banner_core.lua")

local function eq(a, b, msg)
  if a ~= b then
    io.stderr:write("FAIL " .. msg .. ": got " .. tostring(a) .. ", want " .. tostring(b) .. "\n")
    os.exit(1)
  end
end

local function check(cond, msg)
  eq(not not cond, true, msg)
end

-- settings: defaults, validation
local d = core.parse_settings(nil)
eq(d.live_banner, true, "default enabled")
eq(d.banner_position, "top-center", "default position")
eq(d.banner_density, nil, "density is not a setting")
eq(d.banner_animations, true, "default animations")
eq(d.banner_pinned, false, "default pin off")
local s = core.parse_settings({ live_banner = false, banner_position = "bottom-left", banner_density = "full", banner_animations = false })
eq(s.live_banner, false, "banner off")
eq(s.banner_position, "bottom-left", "position kept")
eq(s.banner_density, nil, "density is ignored")
eq(s.banner_animations, false, "animations off")
eq(core.parse_settings({ banner_position = "sideways" }).banner_position, "top-center", "bad position")
eq(core.parse_settings({ banner_density = "huge" }).banner_pinned, false, "bad density does not change the pin")
eq(core.next_density, nil, "no density toggle")
eq(core.controls_layout, nil, "no copy or close controls")
eq(core.wrap, nil, "no transcript wrap")
eq(core.parse_settings({ live_banner = "no" }).live_banner, true, "non-boolean ignored")
eq(core.parse_settings({ banner_pinned = true }).banner_pinned, true, "pin on")
eq(core.parse_settings({ banner_pinned = "yes" }).banner_pinned, false, "non-boolean pin ignored")

-- square status-grid cells: 25 squares inside the icon box, top-left
for i = 0, 24 do
  local box = core.cell_box(i)
  check(box.w == box.h and box.w > 0, "cell is a square")
  check(box.x >= core.PAD and box.y >= core.PAD, "cell inside padding")
  check(box.x + box.w <= core.PAD + core.ICON and box.y + box.h <= core.PAD + core.ICON, "cell inside icon")
end
local first, last = core.cell_box(0), core.cell_box(24)
check(first.x < last.x and first.y < last.y, "cells span the grid")

-- position
local frame = { x = 0, y = 0, w = 1000, h = 800 }
local box = { w = 400, h = 60 }
local function at(p) local r = core.resolve_position(p, frame, box, 10); return r.x .. "," .. r.y end
eq(at("top-center"), "300.0,10", "top-center")
eq(at("top-left"), "10,10", "top-left")
eq(at("top-right"), "590,10", "top-right")
eq(at("bottom-center"), "300.0,730", "bottom-center")
eq(at("bottom-left"), "10,730", "bottom-left")
eq(at("bottom-right"), "590,730", "bottom-right")
eq(at("center"), "300.0,370.0", "center")

-- every banner state has a matrix animation and 25 alphas in range
for state in pairs(core.STATE_MATRIX) do
  check(core.STATE_MATRIX[state], "matrix for " .. state)
  for i = 0, 24 do
    for _, t in ipairs({ 0, 0.37, 1.9 }) do
      local a = core.dot_alpha(state, i, t, true)
      check(a >= 0 and a <= 1, state .. " alpha in range")
    end
  end
end

-- Every pipeline state moves. Animations off holds one frame.
local function frame_key(state, t, animate)
  local parts = {}
  for i = 0, 24 do
    parts[#parts + 1] = string.format("%.3f", core.dot_alpha(state, i, t, animate))
  end
  return table.concat(parts, ",")
end

for state in pairs(core.STATE_MATRIX) do
  local seen = {}
  for _, t in ipairs({ 0, 0.17, 0.33, 0.5, 0.8, 1.1, 1.6, 2.2 }) do
    seen[frame_key(state, t, true)] = true
  end
  local n = 0
  for _ in pairs(seen) do
    n = n + 1
  end
  check(n > 1, state .. " moves")
  for i = 0, 24 do
    eq(
      core.dot_alpha(state, i, 0, false),
      core.dot_alpha(state, i, 9.9, false),
      state .. " still when animations are off"
    )
  end
end

-- Recording is a level meter: bars grow upward and do not share one height.
local function column_energy(col, t)
  local sum = 0
  for row = 0, 4 do
    sum = sum + core.dot_alpha("recording", row * 5 + col, t, true)
  end
  return sum
end

for _, t in ipairs({ 0, 0.4, 0.9, 1.5 }) do
  for col = 0, 4 do
    local prev = -1
    for row = 0, 4 do
      local a = core.dot_alpha("recording", row * 5 + col, t, true)
      check(a + 1e-9 >= prev, "recording bar grows downward")
      prev = a
    end
  end
  eq(
    core.dot_alpha("recording", 0, t, false),
    core.dot_alpha("recording", 0, 0, true),
    "animations off freezes the meter"
  )
end

local rose, fell = false, false
local tallest = {}
for col = 0, 4 do
  local prev
  for step = 0, 20 do
    local energy = column_energy(col, step * 0.12)
    if prev then
      if energy > prev + 0.02 then
        rose = true
      end
      if energy < prev - 0.02 then
        fell = true
      end
    end
    prev = energy
  end
end
check(rose and fell, "recording bars rise and fall")
for step = 0, 16 do
  local best, who = -1, -1
  local t = step * 0.15
  for col = 0, 4 do
    local energy = column_energy(col, t)
    if energy > best then
      best, who = energy, col
    end
  end
  tallest[who] = true
end
local peaks = 0
for _ in pairs(tallest) do
  peaks = peaks + 1
end
check(peaks > 1, "the tall bar moves across the meter")

-- The other marks keep their shape and each move differently.
local function gaps_stay_dim(state)
  for i = 0, 24 do
    if core.dot_alpha(state, i, 0, false) <= 0.15 then
      for _, t in ipairs({ 0.2, 0.7, 1.4 }) do
        eq(core.dot_alpha(state, i, t, true), 0.15, state .. " keeps empty cells dim")
      end
    end
  end
end

for _, state in ipairs({ "transcribing", "rewriting", "error", "warning", "idle" }) do
  gaps_stay_dim(state)
end
eq(core.dot_alpha("error", 0, 3, false), 1, "error still frame is the mark")
eq(core.dot_alpha("error", 1, 3, false), 0.15, "error still frame keeps the gap")
eq(core.dot_alpha("transcribing", 11, 3, false), 1, "dictating still frame is the mark")
eq(core.dot_alpha("rewriting", 2, 3, false), 1, "processing still frame is the ring")
eq(core.dot_alpha("warning", 2, 3, false), 1, "warning still frame is the mark")
eq(core.dot_alpha("idle", 12, 3, false), 0.35, "idle still frame is the quiet square")

local left_then_right = false
local right_then_left = false
if core.dot_alpha("transcribing", 11, 0, true) > core.dot_alpha("transcribing", 13, 0, true) + 0.05 then
  left_then_right = true
end
if core.dot_alpha("transcribing", 13, 0.68, true) > core.dot_alpha("transcribing", 11, 0.68, true) + 0.05 then
  right_then_left = true
end
check(left_then_right and right_then_left, "dictating sweep crosses the mark")

local hottest = {}
local ring = { 2, 8, 14, 18, 22, 16, 10, 6 }
for step = 0, 8 do
  local best, who = -1, -1
  for _, cell in ipairs(ring) do
    local a = core.dot_alpha("rewriting", cell, step * 0.14, true)
    if a > best then
      best, who = a, cell
    end
  end
  hottest[who] = true
end
local heads = 0
for _ in pairs(hottest) do
  heads = heads + 1
end
check(heads > 1, "processing highlight chases the ring")
eq(frame_key("loading", 0.4, true), frame_key("rewriting", 0.4, true), "loading uses the processing chase")
eq(frame_key("pasting", 0.4, true), frame_key("speaking", 0.4, true), "paste and speech share the chase")

check(
  core.dot_alpha("error", 12, 0, true) ~= core.dot_alpha("error", 0, 0, true),
  "error ripple is brighter at the center first"
)
check(
  core.dot_alpha("error", 12, 0, true) ~= core.dot_alpha("error", 12, 0.45, true),
  "error ripple moves"
)
check(core.dot_alpha("warning", 2, 0, true) > core.dot_alpha("warning", 22, 0, true), "warning stem leads")
check(core.dot_alpha("warning", 22, 0.92, true) > core.dot_alpha("warning", 2, 0.92, true), "warning dot flashes")
check(core.dot_alpha("idle", 12, 0, true) ~= core.dot_alpha("idle", 12, 1.3, true), "idle square breathes")
check(core.dot_alpha("idle", 12, 0, true) ~= core.dot_alpha("idle", 6, 0, true), "idle center leads the edge")

local signatures = {}
for _, state in ipairs({ "recording", "transcribing", "rewriting", "error", "warning", "idle" }) do
  local key = frame_key(state, 0.63, true)
  check(signatures[key] == nil, state .. " motion is its own")
  signatures[key] = state
end

-- A wall-clock second is ~1e9. sin of that raw angle sticks on some libm builds
-- and froze the recording meter. The other marks already wrapped their phase.
local real_sin = math.sin
local max_sin_arg = 0
math.sin = function(x)
  local ax = math.abs(x)
  if ax > max_sin_arg then
    max_sin_arg = ax
  end
  if ax > 64 then
    return 0
  end
  return real_sin(x)
end
local wall = 1759440123.2
local function keeps_moving(state, seconds)
  local prev = frame_key(state, wall, true)
  local steps = 0
  local n = math.floor(seconds / 0.2)
  for i = 1, n do
    local now = frame_key(state, wall + i * 0.2, true)
    if now == prev then
      return false
    end
    prev = now
    steps = steps + 1
  end
  return steps == n
end
check(frame_key("recording", wall, true) ~= frame_key("recording", wall + 0.35, true), "recording equalizer moves at a wall clock")
check(max_sin_arg < 64, "recording does not feed the wall clock to sin")
check(keeps_moving("recording", 3), "recording bars keep rising and falling")
check(keeps_moving("loading", 4), "loading keeps moving for the whole load")
check(keeps_moving("rewriting", 4), "processing keeps moving")
check(keeps_moving("pasting", 4), "pasting keeps moving")
check(keeps_moving("transcribing", 4), "dictating keeps moving")
check(keeps_moving("speaking", 4), "dictating keeps moving while speech plays")
local still_load = frame_key("loading", wall, false)
check(frame_key("loading", wall + 0.4, true) ~= still_load, "loading is not the still frame")
math.sin = real_sin

-- view merge
local session = { kind = "dict", start_ms = 1000 }
local snap = { kind = "dict", state = "rewriting", text = "hi", detail = "d", updated_ms = 1500 }
local v = core.pick_view("recording", snap, session)
eq(v.state, "rewriting", "snapshot ahead of local wins")
eq(v.text, "hi", "snapshot text carried")
eq(core.pick_view("transcribing", { kind = "dict", state = "recording", updated_ms = 1500 }, session).state,
  "transcribing", "local ahead of a lagging snapshot")
eq(core.pick_view("cancelling", snap, session).state, "cancelling", "cancelling overrides")
eq(core.pick_view("recording", { kind = "dict", state = "done", text = "old", updated_ms = 900 }, session).state,
  "recording", "stale snapshot ignored")
eq(core.pick_view("recording", { kind = "speak", state = "speaking", updated_ms = 2000 }, session).state,
  "recording", "other kind ignored")
eq(core.pick_view("recording", nil, session).state, "recording", "no snapshot")

-- exit states
local function final(code, snapshot, out, err, cancelling)
  return core.final_view(code, snapshot, session, out, err, cancelling)
end
eq(final(3, nil, "", "").state, "cancelled", "exit 3")
eq(final(0, snap, "x\n", "").state, "done", "exit 0")
eq(final(0, nil, "typed text\n", "").text, "typed text", "stdout fallback")
eq(final(1, { kind = "dict", state = "empty", detail = "n", updated_ms = 2000 }, "", "").state, "empty", "empty")
local e = final(1, nil, "", "digivoice dict: whisper-cli failed (boom)\n")
eq(e.state, "error", "error")
eq(e.detail, "whisper-cli failed (boom)", "prefix stripped")
eq(final(137, nil, "", "", true).state, "cancelled", "killed while cancelling")
eq(final(0, snap, "x", "", true).state, "done", "old CLI that ignored cancel is reported honestly")

-- cancellable: dict until paste, never speak
for _, st in ipairs({ "loading", "recording", "transcribing", "rewriting" }) do
  check(core.cancellable("dict", st), st .. " cancellable")
end
for _, st in ipairs({ "pasting", "done", "cancelling", "error" }) do
  check(not core.cancellable("dict", st), st .. " not cancellable")
end
check(not core.cancellable("speak", "speaking"), "speak not cancellable")

-- Esc key
check(core.is_cancel_key(53, {}), "plain Esc")
check(not core.is_cancel_key(53, { cmd = true }), "cmd+Esc is not ours")
check(not core.is_cancel_key(53, { shift = true }), "shift+Esc is not ours")
check(not core.is_cancel_key(36, {}), "other key")

-- layout is the icon only
local side = core.PAD * 2 + core.ICON
local short = core.layout({ state = "rewriting", text = "short text", detail = "" }, "dict", "full")
eq(short.body, "", "no status word")
eq(short.phase, "processing", "rewriting is the processing icon")
eq(#short.lines, 0, "no text lines")
eq(short.clipped, false, "not clipped")
eq(short.raw, "", "no transcript kept for copy")
eq(short.hint, nil, "no chrome hints")
eq(short.title, nil, "no chrome title")
eq(short.w, side, "icon only")
eq(short.h, side, "icon only")
local long_text = string.rep("word ", 200)
local retracted = core.layout({ state = "rewriting", text = long_text, detail = "" }, "dict", "retract")
local open = core.layout({ state = "rewriting", text = long_text, detail = "" }, "dict", "full")
eq(open.w, retracted.w, "density does not widen the icon")
eq(open.phase, retracted.phase, "full does not show the transcript")
local grid = core.layout({ state = "recording", text = "ignored", detail = "" }, "dict", "retract")
eq(grid.phase, "recording", "recording icon")
eq(grid.w, side, "recording hugs the grid")
eq(core.layout({ state = "transcribing", text = "words", detail = "" }, "dict", "retract").phase, "dictating", "dictating icon")
eq(core.layout({ state = "speaking", text = "said", detail = "" }, "speak", "full").phase, "processing", "speech is processing")
local quiet = core.layout({ state = "done", text = "final words", detail = "" }, "dict", "full")
eq(quiet.body, "", "done has no status word")
eq(quiet.phase, "idle", "done settles to the idle icon")
eq(quiet.w, side, "done hugs the grid")
eq(core.layout({ state = "idle", text = "nope", detail = "" }, "dict", "full").phase, "idle", "idle icon")
eq(core.layout({ state = "error", text = "boom", detail = "long" }, "dict", "retract").phase, "error", "error icon")
eq(core.layout({ state = "empty", text = "", detail = "n" }, "dict", "full").phase, "", "nothing to show has no icon")
eq(core.layout({ state = "warning", text = "", detail = "n" }, "dict", "full").phase, "warning", "warning icon")
eq(core.icon_phase("bogus"), "", "unknown state has no icon")
check(core.should_draw("recording", false), "recording shows while retracted")
check(core.should_draw("transcribing", false), "dictating shows while retracted")
check(core.should_draw("loading", false), "loading is processing")
check(core.should_draw("rewriting", false), "processing shows while retracted")
check(core.should_draw("pasting", false), "pasting shows")
check(core.should_draw("speaking", false), "speaking shows")
check(core.should_draw("error", false), "a current error shows")
check(core.should_draw("warning", false), "a current warning shows")
check(not core.should_draw("empty", false), "nothing to show hides")
check(not core.should_draw("pending", false), "pending hides")
check(not core.should_draw("recording", false, true), "a pending flag hides even recording")
check(not core.should_draw("idle", false), "idle stays hidden unless pinned")
check(core.should_draw("idle", true), "pinned idle stays visible")
check(not core.should_draw("idle", true, true), "pending hides a pinned idle icon")
check(not core.should_draw("done", false), "a finished take retracts")
local routes = {
  { "launch", false },
  { "pin_on", true },
  { "pin_off", false },
  { "show", true },
  { "hide", false },
  { "toggle", true },
  { "take_start", false },
  { "recording", true },
  { "transcribing", true },
  { "loading", true },
  { "rewriting", true },
  { "pasting", true },
  { "speaking", true },
  { "empty", false },
  { "error", true },
  { "warning", true },
  { "take_end", false },
  { "pending", false },
}
for _, row in ipairs(routes) do
  eq(core.route_banner(row[1], {}), row[2], "route " .. row[1])
end
eq(core.route_banner("launch", { pinned = true }), true, "launch with pin shows idle")
eq(core.route_banner("take_end", { pinned = true }), true, "pin keeps idle after the take")
eq(core.route_banner("show", { pending = true }), false, "pending hides a show")
eq(core.route_banner("toggle", { showing = true }), false, "toggle hides when it is up")
eq(core.route_banner("recording", { pending = true }), false, "pending hides recording")
eq(core.focus_action(true), "focus", "an open terminal is focused")
eq(core.focus_action(false), "open", "a missing terminal is opened")
eq(core.focus_action(false), "open", "a second call still opens once per click")
check(core.tui_is_open("4242\n"), "a pid means the terminal is open")
check(not core.tui_is_open(""), "blank pid is closed")
check(not core.tui_is_open("nope"), "a non-pid is closed")

-- linger follows the pin
eq(core.linger_seconds("done", false), 0, "a finished take hides")
eq(core.linger_seconds("done"), 0, "unpinned done hides")
eq(core.linger_seconds("error", false), 4.0, "an error stays while it is current")
eq(core.linger_seconds("cancelled", false), 0, "cancel hides")
eq(core.linger_seconds("recording", false), nil, "recording stays while voice is in use")
eq(core.linger_seconds("transcribing", false), nil, "dictating stays")
eq(core.linger_seconds("done", true), 1.2, "pin settles done to idle")
eq(core.linger_seconds("error", true), nil, "pin keeps an error")
eq(core.linger_seconds("idle", true), nil, "pin keeps the idle icon")

local hug = core.layout({ state = "rewriting", text = "short text", detail = "" })
eq(hug.w, side, "icon stays the grid")
local cell0 = core.cell_box(0)
check(math.abs(cell0.x - core.PAD) < core.PAD and math.abs(cell0.y - core.PAD) < core.PAD, "grid top-left with even pad")
local a = core.layout({ state = "recording", text = "same longest line here yes\nshort", detail = "" }, "dict", "full", { screen_h = 900 })
local b = core.layout({ state = "recording", text = string.rep("word ", 80), detail = "" }, "dict", "full", { screen_h = 200 })
eq(a.w, b.w, "transcript length does not change the banner")
eq(a.phase, "recording", "recording icon")
check(b.h < 80, "status banner stays a single icon")
eq(b.clipped, false, "an icon does not scroll")

-- theme chrome flips, status colors stay (RYG untouched by theme)
-- Dark is the remock canvas #000; light is ivory paper #F9F8F6.
eq(core.theme_colors("dark").bg.red, 0, "remock dark ground")
eq(core.theme_colors("dark").bg.green, 0, "remock dark ground green")
eq(core.theme_colors("dark").bg.blue, 0, "remock dark ground blue")
check(math.abs(core.theme_colors("dark").text.red - 0xED / 255) < 0.002, "remock dark ink")
check(math.abs(core.theme_colors("light").bg.red - 0xF9 / 255) < 0.002, "ivory light ground")
check(math.abs(core.theme_colors("light").bg.green - 0xF8 / 255) < 0.002, "ivory light ground green")
check(math.abs(core.theme_colors("light").bg.blue - 0xF6 / 255) < 0.002, "ivory light ground blue")
check(core.theme_colors("bogus").bg.red == 0, "unknown theme falls back to dark")
eq(core.matrix_for("recording").color.red, 0.94, "recording red stays")

local tokyo = core.theme_colors("dark", "tokyonight")
check(math.abs(tokyo.bg.red - 0x1a / 255) < 0.002, "tokyonight ground")
check(math.abs(tokyo.bg.green - 0x1b / 255) < 0.002, "tokyonight ground green")
check(math.abs(tokyo.bg.blue - 0x26 / 255) < 0.002, "tokyonight ground blue")
check(math.abs(tokyo.border.red - 0xff / 255) < 0.002, "tokyonight border")
check(math.abs(tokyo.border.green - 0x9e / 255) < 0.002, "tokyonight border green")
check(math.abs(tokyo.border.blue - 0x64 / 255) < 0.002, "tokyonight border blue")
check(math.abs(tokyo.accent.red - 0x7a / 255) < 0.002, "tokyonight primary")
check(math.abs(tokyo.accent.green - 0xa2 / 255) < 0.002, "tokyonight primary green")
check(math.abs(tokyo.accent.blue - 0xf7 / 255) < 0.002, "tokyonight primary blue")
eq(core.theme_colors("dark", "").bg.red, 0, "empty palette stays on legacy ground")
eq(core.theme_colors("dark", "").border.green, 1, "empty palette stays on legacy border")
eq(core.matrix_for("recording").color.red, 0.94, "matrix red is still the empty-palette grid")

-- 9 anchors, snap, clamp, saved, reanchor
local frame9 = { x = 0, y = 0, w = 1440, h = 900 }
local size9 = { w = 100, h = 50 }
eq(#core.anchors(frame9, size9, 16), 9, "nine anchors")
local snapped = core.snap_position(20, 20, frame9, size9, 16)
eq(snapped.anchor, "tl", "snaps near tl")
eq(snapped.x, 16, "snap x")
local free = core.snap_position(700, 400, frame9, size9, 16)
eq(free.anchor, nil, "mid-screen stays free")
local clamped = core.clamp_position(-50, 9999, frame9, size9, 16)
eq(clamped.x, 16, "clamp left")
eq(clamped.y, 900 - 50 - 16, "clamp bottom")
check(core.resolve_saved(nil, frame9, size9, 16) == nil, "nothing persisted")
local kept = core.resolve_saved({ x = 100, y = 100, anchor = "c" }, frame9, size9, 16)
eq(kept.x, 100, "saved position kept")
eq(kept.anchor, "c", "saved anchor kept")
eq(core.anchor_for_position("middle-left"), "ml", "setting maps to anchor")
eq(core.anchor_for_position("bogus"), "tc", "bad setting maps to default anchor")
local rc = core.reanchor({ x = 100, y = 100, w = 38, h = 38 }, { w = 200, h = 100 }, "c")
eq(rc.x, 100 + 19 - 100, "center x kept on expand")
eq(rc.y, 100 + 19 - 50, "center y kept on expand")
local rl = core.reanchor({ x = 16, y = 16, w = 38, h = 38 }, { w = 200, h = 38 }, "tl")
eq(rl.x, 16, "left pin grows right")
local rr = core.reanchor({ x = 100, y = 16, w = 38, h = 38 }, { w = 200, h = 38 }, "tr")
eq(rr.x, 100 + 38 - 200, "right pin grows left")
local rf = core.reanchor({ x = 300, y = 300, w = 38, h = 38 }, { w = 200, h = 100 }, nil)
eq(rf.x, 300, "free float keeps top-left")
eq(rf.y, 300, "free float keeps top-left")

-- launch notice lists commands and the cli
local notice = core.launch_notice("/x/digivoice")
check(notice:find("Esc", 1, true) and notice:find("cli: /x/digivoice", 1, true), "launch notice")

print("PASS banner_core")
