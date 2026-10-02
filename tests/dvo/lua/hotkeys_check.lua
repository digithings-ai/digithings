-- Pure-logic checks for digivoice/hammerspoon/hotkeys.lua. Env: ADAPTER_DIR.
local hotkeys = dofile(os.getenv("ADAPTER_DIR") .. "/hotkeys.lua")

local function eq(a, b, msg)
  if a ~= b then
    io.stderr:write("FAIL " .. msg .. ": got " .. tostring(a) .. ", want " .. tostring(b) .. "\n")
    os.exit(1)
  end
end

local function check(cond, msg)
  eq(not not cond, true, msg)
end

local defaults = hotkeys.defaults()
eq(defaults.dictation.keycode, 61, "default dictation is Right Option")
eq(defaults.dictation.kind, "flags", "Right Option is a flags key")
eq(defaults.dictation.alt, true, "Right Option sets alt")
eq(defaults.dictation.double, false, "Right Option is a single press")
eq(defaults.speak.keycode, 58, "default speak is Left Option")
eq(defaults.speak.double, true, "speak is a double tap")
eq(defaults.cancel.keycode, 53, "default cancel is Esc")
eq(defaults.cancel.kind, "key", "Esc is a key")

local chord = hotkeys.parse_binding("ctrl+shift+space")
check(chord, "ctrl+shift+space parses")
eq(chord.keycode, 49, "space keycode")
eq(chord.kind, "key", "a chord is a keyDown")
eq(chord.ctrl, true, "ctrl")
eq(chord.shift, true, "shift")
eq(chord.alt, false, "no alt")
eq(chord.cmd, false, "no cmd")
check(hotkeys.flags_match(chord, { ctrl = true, shift = true }), "exact chord flags")
check(not hotkeys.flags_match(chord, { ctrl = true, shift = true, cmd = true }), "extra modifier misses")
check(not hotkeys.flags_match(chord, { ctrl = true }), "missing shift misses")

eq(hotkeys.parse_binding("Right Option").keycode, 61, "typed Right Option")
eq(hotkeys.parse_binding("option").keycode, 61, "bare option is Right Option")
eq(hotkeys.parse_binding("alt").kind, "flags", "bare alt is Right Option")
eq(hotkeys.parse_binding("Left Option").keycode, 58, "typed Left Option")
eq(hotkeys.parse_binding("Double-tap Left Option").double, true, "typed double-tap")
eq(hotkeys.parse_binding("Esc").keycode, 53, "typed Esc")
eq(hotkeys.parse_binding("ctrl+shift+s").keycode, 1, "s keycode")
eq(hotkeys.parse_binding("ctrl+shift+x").keycode, 7, "x keycode")
check(hotkeys.parse_binding("!!!") == nil, "garbage is not a key")
check(hotkeys.parse_binding("ctrl+shift") == nil, "modifiers alone are not a key")
check(hotkeys.parse_binding("") == nil, "blank is not a key")

local next_specs, warnings = hotkeys.apply(defaults, { dictation = "!!!" })
eq(next_specs.dictation.keycode, 61, "bad dictation keeps Right Option")
eq(next_specs.speak.double, true, "untouched speak stays")
eq(#warnings, 1, "one warning")
check(warnings[1]:find("!!!", 1, true), "warning names the bad text")
check(warnings[1]:find("Right Option", 1, true), "warning names the kept bind")

local remapped = hotkeys.apply(defaults, {
  dictation = "ctrl+shift+space",
  speak = "ctrl+shift+s",
  cancel = "ctrl+shift+x",
})
eq(remapped.dictation.keycode, 49, "remap replaces dictation")
eq(remapped.speak.keycode, 1, "remap replaces speak")
eq(remapped.cancel.keycode, 7, "remap replaces cancel")
check(not hotkeys.matches(remapped.dictation, 61, { alt = true }), "Right Option does not match the remap")

local nested = hotkeys.bindings_from_settings({
  hotkey_bindings = { dictation = "ctrl+shift+space", speak = "Esc", cancel = "Esc" },
})
eq(nested.dictation, "ctrl+shift+space", "nested settings")
local flat = hotkeys.bindings_from_settings({ dictation = "ctrl+shift+space", banner_pinned = true })
eq(flat.dictation, "ctrl+shift+space", "flat settings")
check(hotkeys.bindings_from_settings({ banner_pinned = true }) == nil, "no binds means keep previous")
check(hotkeys.bindings_from_settings(nil) == nil, "missing file")

check(hotkeys.suspended("1"), "capture flag suspends hotkeys")
check(hotkeys.suspended("1\n"), "capture flag ignores trailing newline")
check(hotkeys.suspended("true"), "capture flag accepts true")
check(not hotkeys.suspended(""), "empty flag keeps hotkeys armed")
check(not hotkeys.suspended("0"), "zero keeps hotkeys armed")
check(not hotkeys.suspended(nil), "a missing flag keeps hotkeys armed")

print("PASS hotkeys")
