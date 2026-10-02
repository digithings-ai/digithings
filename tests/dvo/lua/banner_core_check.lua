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
eq(d.banner_density, "retract", "default density")
eq(d.banner_animations, true, "default animations")
eq(d.banner_pinned, false, "default pin off")
local s = core.parse_settings({ live_banner = false, banner_position = "bottom-left", banner_density = "full", banner_animations = false })
eq(s.live_banner, false, "banner off")
eq(s.banner_position, "bottom-left", "position kept")
eq(s.banner_density, "full", "density kept")
eq(s.banner_animations, false, "animations off")
eq(core.parse_settings({ banner_position = "sideways" }).banner_position, "top-center", "bad position")
eq(core.parse_settings({ banner_density = "huge" }).banner_density, "retract", "bad density")
eq(core.parse_settings({ banner_density = "mini" }).banner_density, "retract", "legacy mini rejected")
eq(core.parse_settings({ banner_density = "peek" }).banner_density, "retract", "legacy peek rejected")
eq(core.parse_settings({ live_banner = "no" }).live_banner, true, "non-boolean ignored")
eq(core.parse_settings({ banner_pinned = true }).banner_pinned, true, "pin on")
eq(core.parse_settings({ banner_pinned = "yes" }).banner_pinned, false, "non-boolean pin ignored")

-- density click toggle: retract → full → retract
eq(core.next_density("retract"), "full", "retract expands")
eq(core.next_density("full"), "retract", "full collapses")
eq(core.next_density("bogus"), "retract", "bogus collapses to retract")

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

-- recording is a still icon; processing may blink. Animations off freezes every state.
local moving = false
for i = 0, 24 do
  if core.dot_alpha("recording", i, 0, true) ~= core.dot_alpha("recording", i, 0.3, true) then
    moving = true
  end
  eq(core.dot_alpha("recording", i, 0, false), core.dot_alpha("recording", i, 9.9, false), "still frame")
end
check(not moving, "recording icon is still")
check(core.dot_alpha("rewriting", 2, 0, true) ~= core.dot_alpha("rewriting", 2, 0.7, true), "processing icon blinks")
eq(core.dot_alpha("error", 0, 0, true), 1, "error glyph dot on")
eq(core.dot_alpha("error", 1, 0, true), 0.15, "error glyph dot off")

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

-- wrap / layout
local lines = core.wrap("one two three four five six seven", 12)
eq(#lines, 4, "wrap count")
eq(lines[1], "one two", "wrap line 1")
eq(#core.wrap(string.rep("x", 30), 10), 3, "long word hard split")
eq(#core.wrap("a\n\nb", 10), 2, "blank lines dropped")

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
eq(core.layout({ state = "empty", text = "", detail = "n" }, "dict", "full").phase, "warning", "warning icon")
eq(core.icon_phase("bogus"), "", "unknown state has no icon")
eq(core.next_density("bogus"), "retract", "unknown density collapses")
check(core.should_draw("recording", false), "recording shows while retracted")
check(core.should_draw("transcribing", false), "dictating shows while retracted")
check(core.should_draw("rewriting", false), "processing shows while retracted")
check(core.should_draw("error", false), "a current error shows")
check(core.should_draw("empty", false), "a current warning shows")
check(not core.should_draw("idle", false), "idle stays hidden unless pinned")
check(core.should_draw("idle", true), "pinned idle stays visible")
check(not core.should_draw("done", false), "a finished take retracts")
eq(core.focus_action(true), "focus", "an open terminal is focused")
eq(core.focus_action(false), "open", "a missing terminal is opened")
eq(core.focus_action(false), "open", "a second call still opens once per click")
check(core.tui_is_open("4242\n"), "a pid means the terminal is open")
check(not core.tui_is_open(""), "blank pid is closed")
check(not core.tui_is_open("nope"), "a non-pid is closed")

-- linger follows the pin, not density
eq(core.linger_seconds("done", "full"), 0, "full density does not keep a finished take")
eq(core.linger_seconds("done", "retract"), 0, "retract hides when the take is done")
eq(core.linger_seconds("error", "full"), 4.0, "an error stays while it is current")
eq(core.linger_seconds("cancelled", "retract"), 0, "cancel retracts")
eq(core.linger_seconds("recording", "retract"), nil, "recording stays while voice is in use")
eq(core.linger_seconds("transcribing", "retract"), nil, "dictating stays")
eq(core.linger_seconds("done", "retract", true), 1.2, "pin settles done to idle")
eq(core.linger_seconds("error", "retract", true), nil, "pin keeps an error")
eq(core.linger_seconds("idle", "retract", true), nil, "pin keeps the idle icon")

eq(core.body_for({ state = "cancelled", text = "kept", detail = "" }), "", "no cancel word")
eq(core.body_for({ state = "empty", text = "kept", detail = "n" }), "", "no warning word")
eq(core.body_for({ state = "error", text = "kept", detail = "boom" }), "", "no error word")
eq(core.body_for({ state = "rewriting", text = "hi", detail = "preset" }), "", "no transcript")
local hug = core.layout({ state = "rewriting", text = "short text", detail = "" }, "dict", "full")
eq(hug.w, side, "icon stays the grid")
local cell0 = core.cell_box(0)
check(math.abs(cell0.x - core.PAD) < core.PAD and math.abs(cell0.y - core.PAD) < core.PAD, "grid top-left with even pad")
local a = core.layout({ state = "recording", text = "same longest line here yes\nshort", detail = "" }, "dict", "full", { screen_h = 900 })
local b = core.layout({ state = "recording", text = string.rep("word ", 80), detail = "" }, "dict", "full", { screen_h = 200 })
eq(a.w, b.w, "transcript length does not change the banner")
eq(a.phase, "recording", "recording icon")
eq(core.full_max_lines(900), 23, "50vh budget helper still matches a normal screen")
eq(core.full_max_lines(200), 4, "small screen helper still clamps")
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

-- the banner has no controls
local retract_ctl = core.controls_layout(38, 38, "retract")
eq(retract_ctl.dir, "none", "no control row")
eq(#retract_ctl.buttons, 0, "no pin button")
eq(#core.controls_layout(280, 60, "full").buttons, 0, "full has no pin either")
eq(core.controls_height("retract"), 0, "no pin gutter")
eq(core.controls_height("full"), 0, "no pin gutter when full")

-- launch notice lists commands and the cli
local notice = core.launch_notice("/x/digivoice")
check(notice:find("Esc", 1, true) and notice:find("cli: /x/digivoice", 1, true), "launch notice")

print("PASS banner_core")
