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
eq(d.banner_animations, true, "default animations")
local s = core.parse_settings({ live_banner = false, banner_position = "bottom-left", banner_animations = false })
eq(s.live_banner, false, "banner off")
eq(s.banner_position, "bottom-left", "position kept")
eq(s.banner_animations, false, "animations off")
eq(core.parse_settings({ banner_position = "sideways" }).banner_position, "top-center", "bad position")
eq(core.parse_settings({ live_banner = "no" }).live_banner, true, "non-boolean ignored")

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

local short = core.layout({ state = "rewriting", text = "short text", detail = "" }, "dict", false)
eq(#short.lines, 1, "short text one line")
eq(short.clipped, false, "not clipped")
eq(short.hint, "Esc to cancel", "cancel hint while cancellable")
local long_text = string.rep("word ", 200)
local long = core.layout({ state = "rewriting", text = long_text, detail = "" }, "dict", false)
eq(#long.lines, core.LINES_COLLAPSED, "collapsed limit")
check(long.clipped and long.expandable, "long text is expandable")
local open = core.layout({ state = "rewriting", text = long_text, detail = "" }, "dict", true)
check(open.w > long.w and #open.lines > #long.lines and open.h > long.h, "expanded is bigger")
local idle = core.layout({ state = "recording", text = "", detail = "" }, "dict", false)
eq(#idle.lines, 0, "recording has no body")
eq(idle.h, core.PAD * 2 + core.ICON, "compact height")
eq(core.layout({ state = "done", text = "x", detail = "" }, "dict", false).hint, nil, "no hint when done")

-- launch notice lists commands and the cli
local notice = core.launch_notice("/x/digivoice")
check(notice:find("Esc", 1, true) and notice:find("cli: /x/digivoice", 1, true), "launch notice")

print("PASS banner_core")
