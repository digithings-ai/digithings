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
eq(d.banner_density, "peek", "default density")
eq(d.banner_animations, true, "default animations")
local s = core.parse_settings({ live_banner = false, banner_position = "bottom-left", banner_density = "full", banner_animations = false })
eq(s.live_banner, false, "banner off")
eq(s.banner_position, "bottom-left", "position kept")
eq(s.banner_density, "full", "density kept")
eq(s.banner_animations, false, "animations off")
eq(core.parse_settings({ banner_position = "sideways" }).banner_position, "top-center", "bad position")
eq(core.parse_settings({ banner_density = "huge" }).banner_density, "peek", "bad density")
eq(core.parse_settings({ live_banner = "no" }).live_banner, true, "non-boolean ignored")

-- density click cycle: mini → peek → full → mini
eq(core.next_density("mini"), "peek", "mini expands")
eq(core.next_density("peek"), "full", "peek expands")
eq(core.next_density("full"), "mini", "full collapses")
eq(core.next_density("bogus"), "mini", "bogus collapses to mini")

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

-- every banner state has a matrix animation, a label, and 25 alphas in range
for state in pairs(core.LABELS) do
  check(core.STATE_MATRIX[state], "matrix for " .. state)
  for i = 0, 24 do
    for _, t in ipairs({ 0, 0.37, 1.9 }) do
      local a = core.dot_alpha(state, i, t, true)
      check(a >= 0 and a <= 1, state .. " alpha in range")
    end
  end
end

-- animation vs still frame
local moving = false
for i = 0, 24 do
  if core.dot_alpha("recording", i, 0, true) ~= core.dot_alpha("recording", i, 0.3, true) then
    moving = true
  end
  eq(core.dot_alpha("recording", i, 0, false), core.dot_alpha("recording", i, 9.9, false), "still frame")
end
check(moving, "recording wave animates")
-- glyph states: only glyph dots are bright
eq(core.dot_alpha("done", 3 * 5 + 0, 0, true), 1, "check glyph dot on")
eq(core.dot_alpha("done", 0, 0, true), 0.15, "check glyph dot off")

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

-- wrap / clip / layout
local lines = core.wrap("one two three four five six seven", 12)
eq(#lines, 4, "wrap count")
eq(lines[1], "one two", "wrap line 1")
eq(#core.wrap(string.rep("x", 30), 10), 3, "long word hard split")
eq(#core.wrap("a\n\nb", 10), 2, "blank lines dropped")
local clipped, was = core.clip_lines({ "a", "b", "c", "d" }, 2, 10)
eq(#clipped, 2, "clip count")
eq(was, true, "clip flag")
eq(clipped[2], "b…", "ellipsis")

local short = core.layout({ state = "rewriting", text = "short text", detail = "" }, "dict", "peek")
eq(#short.lines, 1, "short text one line")
eq(short.clipped, false, "not clipped")
eq(short.hint, nil, "no chrome hints")
eq(short.title, nil, "no chrome title")
local long_text = string.rep("word ", 200)
local long = core.layout({ state = "rewriting", text = long_text, detail = "" }, "dict", "peek")
eq(#long.lines, core.LINES_COLLAPSED, "peek glimpse limit")
check(long.clipped, "long text is clipped in peek")
local open = core.layout({ state = "rewriting", text = long_text, detail = "" }, "dict", "full")
check(open.w > long.w and #open.lines > #long.lines and open.h > long.h, "full is bigger")
local mini = core.layout({ state = "recording", text = "ignored", detail = "" }, "dict", "mini")
eq(#mini.lines, 0, "mini is grid only")
eq(mini.body, "", "mini has no text")
eq(mini.w, core.PAD * 2 + core.ICON, "mini hugs the grid")
eq(mini.h, core.PAD * 2 + core.ICON, "mini hugs the grid")
local idle = core.layout({ state = "recording", text = "", detail = "" }, "dict", "peek")
eq(#idle.lines, 0, "recording has no body")
eq(idle.h, core.PAD * 2 + core.ICON, "compact height")
eq(core.next_density("bogus"), "mini", "unknown density collapses")

-- linger: full stays (nil = no auto-hide); peek/mini dismiss after a few seconds
eq(core.linger_seconds("done", "full"), nil, "full stays")
eq(core.linger_seconds("error", "full"), nil, "full stays on error")
eq(core.linger_seconds("done", "peek"), 4.0, "peek dismisses after a few seconds")
eq(core.linger_seconds("done", "mini"), 4.0, "mini dismisses too")
eq(core.linger_seconds("cancelled", "peek"), 1.2, "cancelled clears fast")

-- hug widths: short text stays far under the caps, empty hugs the grid
local hug = core.layout({ state = "rewriting", text = "short text", detail = "" }, "dict", "peek")
check(hug.w < core.WIDTH_COLLAPSED, "peek hugs short text")
check(hug.w > core.PAD * 2 + core.ICON, "peek wider than grid-only")
eq(hug.h, core.PAD * 2 + math.max(core.ICON, core.LINE_HEIGHT), "one line hugs the grid row")
local hug_empty = core.layout({ state = "recording", text = "", detail = "" }, "dict", "peek")
eq(hug_empty.w, core.PAD * 2 + core.ICON, "empty hugs the grid")
eq(hug_empty.h, core.PAD * 2 + core.ICON, "empty hugs the grid")
-- equal padding all densities: grid cell origin sits at PAD
local cell0 = core.cell_box(0)
check(math.abs(cell0.x - core.PAD) < core.PAD and math.abs(cell0.y - core.PAD) < core.PAD, "grid top-left with even pad")
-- uniform line widths
for _, line in ipairs(hug.lines) do
  eq(#line, hug.longest, "lines share one uniform width")
end
-- first line locks the final width: same longest line, same width
local a = core.layout({ state = "done", text = "same longest line here yes\nshort", detail = "" }, "dict", "full", { screen_h = 900 })
local b = core.layout({ state = "done", text = "same longest line here yes\nshort plus more", detail = "" }, "dict", "full", { screen_h = 900 })
eq(a.w, b.w, "width locks from the longest line")
-- full caps near half the viewport: tiny screen clamps the line budget
eq(core.full_max_lines(900), 23, "50vh budget on a normal screen")
eq(core.full_max_lines(200), 4, "small screen clamps lines")
local tall = core.layout(
  { state = "rewriting", text = string.rep("word ", 400), detail = "" }, "dict", "full", { screen_h = 200 }
)
check(tall.h <= 100, "short screen caps full height at 50vh")
check(tall.clipped, "overflow is marked for the scroll window")
check(#tall.all > #tall.lines, "scroll keeps lines past the window")
-- full skips the peek ellipsis: the window is a plain slice for scrolling
for _, line in ipairs(tall.lines) do
  check(not line:find("…", 1, true), "no mid-list ellipsis in full")
end

-- theme chrome flips, status colors stay (RYG untouched by theme)
check(core.theme_colors("dark").bg.red < 0.1, "dark pill")
check(core.theme_colors("light").bg.red > 0.9, "light pill")
check(core.theme_colors("bogus").bg.red < 0.1, "unknown theme falls back to dark")
eq(core.matrix_for("recording").color.red, 0.94, "recording red stays")

-- typewriter slices
local tw = core.tw_slice("hello", 2)
eq(tw.shown, "he", "caret prefix")
eq(tw.done, false, "not done")
eq(core.tw_slice("hello", 99).done, true, "clamped caret finishes")
eq(core.tw_slice("hello", 0).shown, "", "zero caret shows nothing")

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

-- hover controls: mini stacks centered, wider rows right-aligned
local mini_ctl = core.controls_layout(38, 38, "mini")
eq(mini_ctl.dir, "stack", "mini stacks")
eq(mini_ctl.buttons[1].x, mini_ctl.buttons[2].x, "stack shares x")
check(mini_ctl.buttons[2].y > mini_ctl.buttons[1].y, "stack grows down")
eq(mini_ctl.buttons[1].x, (38 - 18) / 2, "stack centered")
local wide_ctl = core.controls_layout(280, 60, "peek")
eq(wide_ctl.dir, "row", "wider rows")
eq(wide_ctl.buttons[1].y, wide_ctl.buttons[2].y, "row shares y")
eq(wide_ctl.buttons[1].x + 18 + 4 + 18, 280, "row right-aligned")
eq(core.controls_height("mini"), 4 + 18 * 2 + 4, "stack height")
eq(core.controls_height("peek"), 4 + 18, "row height")

-- launch notice lists commands and the cli
local notice = core.launch_notice("/x/digivoice")
check(notice:find("Esc", 1, true) and notice:find("cli: /x/digivoice", 1, true), "launch notice")

print("PASS banner_core")
