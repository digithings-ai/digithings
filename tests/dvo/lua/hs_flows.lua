-- Drives digivoice/hammerspoon/init.lua against a fake `hs` so the banner, Esc cancel,
-- and background-only rules (no toast / menubar / Dock) can be checked without a Mac.
-- Usage: lua hs_flows.lua <scenario>   (env: DIGIVOICE_DATA_DIR, DIGIVOICE_BIN)

local scenario = arg[1]
local DATA = os.getenv("DIGIVOICE_DATA_DIR")
local ROOT = arg[0]:match("(.*)/tests/dvo/lua/") or "."
local ADAPTER = ROOT .. "/digivoice/hammerspoon/"

local function fail(msg)
  io.stderr:write("FAIL " .. tostring(scenario) .. ": " .. msg .. "\n")
  os.exit(1)
end

local function check(cond, msg)
  if not cond then
    fail(msg)
  end
end

local function eq(a, b, msg)
  if a ~= b then
    fail((msg or "values differ") .. ": got " .. tostring(a) .. ", want " .. tostring(b))
  end
end

-- Tiny JSON reader: flat objects of strings / numbers / booleans (all status.json needs).
local function json_decode(text)
  local out = {}
  for key, str in text:gmatch('"([%w_]+)"%s*:%s*"(.-)"') do
    out[key] = str:gsub("\\n", "\n")
  end
  for key, num in text:gmatch('"([%w_]+)"%s*:%s*(%-?%d+%.?%d*)') do
    out[key] = tonumber(num)
  end
  for key, bool in text:gmatch('"([%w_]+)"%s*:%s*(%a+)') do
    if bool == "true" then
      out[key] = true
    elseif bool == "false" then
      out[key] = false
    end
  end
  return out
end

local clock = 1000.0
local timers = {}
local notifications = {}
local canvases = {}
local menubars = {}
local tasks = {}
local taps = {}
local mouse_pos = { x = 700, y = 100 }
local mouse_buttons = { left = false }

local function make_timer(interval, fn, repeating)
  local timer = { interval = interval, fn = fn, repeating = repeating, due = clock + interval, live = true }
  function timer:stop()
    self.live = false
  end
  timers[#timers + 1] = timer
  return timer
end

local function advance(seconds)
  local target = clock + seconds
  while true do
    local nxt
    for _, timer in ipairs(timers) do
      if timer.live and timer.due <= target and (not nxt or timer.due < nxt.due) then
        nxt = timer
      end
    end
    if not nxt then
      break
    end
    clock = nxt.due
    if nxt.repeating then
      nxt.due = nxt.due + nxt.interval
    else
      nxt.live = false
    end
    nxt.fn()
  end
  clock = target
end

local function new_canvas(frame)
  local c = { frame = frame, elements = {}, deleted = false, shown = false, clickActivating = nil }
  local methods = {}
  function methods.appendElements(self, ...)
    for _, arg_ in ipairs({ ... }) do
      if arg_.type then
        self.elements[#self.elements + 1] = arg_
      else
        for _, el in ipairs(arg_) do
          self.elements[#self.elements + 1] = el
        end
      end
    end
    return self
  end
  function methods.level(self) return self end
  function methods.behavior(self) return self end
  function methods.clickActivating(self, flag)
    self.clickActivating = flag
    return self
  end
  function methods.mouseCallback(self, fn)
    self.mouse = fn
    return self
  end
  function methods.topLeft(self, pt)
    if pt then
      self.frame.x, self.frame.y = pt.x, pt.y
      return self
    end
    return { x = self.frame.x, y = self.frame.y }
  end
  function methods.frame(self) return self.frame end
  function methods.show(self)
    self.shown = true
    return self
  end
  function methods.delete(self)
    self.deleted = true
  end
  setmetatable(c, {
    __index = function(t, k)
      if type(k) == "number" then
        return rawget(t, "elements")[k]
      end
      return methods[k]
    end,
  })
  canvases[#canvases + 1] = c
  return c
end

local function live_canvas()
  local last = canvases[#canvases]
  if last and not last.deleted then
    return last
  end
  return nil
end

local dockicon_hidden = false

hs = {
  dockicon = {
    hide = function() dockicon_hidden = true end,
    show = function() dockicon_hidden = false end,
  },
  fs = {
    pathToAbsolute = function(p) return p end,
    mkdir = function(p) os.execute('mkdir -p "' .. p .. '"') end,
  },
  json = {
    read = function(path)
      local f = io.open(path, "r")
      if not f then return nil end
      local text = f:read("*a")
      f:close()
      return json_decode(text)
    end,
  },
  timer = {
    secondsSinceEpoch = function() return clock end,
    doEvery = function(interval, fn) return make_timer(interval, fn, true) end,
    doAfter = function(delay, fn) return make_timer(delay, fn, false) end,
  },
  notify = {
    new = function(spec)
      return { send = function() notifications[#notifications + 1] = spec end }
    end,
  },
  screen = {
    mainScreen = function()
      return { frame = function() return { x = 0, y = 0, w = 1440, h = 900 } end }
    end,
  },
  image = { imageFromPath = function() return nil end },
  menubar = {
    new = function()
      local m = { title = "", deleted = false }
      function m:setTitle(t) self.title = t end
      function m:setIcon() end
      function m:delete() self.deleted = true end
      menubars[#menubars + 1] = m
      return m
    end,
  },
  canvas = {
    new = new_canvas,
    windowLevels = { overlay = 1 },
    windowBehaviors = { canJoinAllSpaces = 1 },
  },
  task = {
    new = function(bin, cb, args)
      local t = { bin = bin, cb = cb, args = args, running = false, killed = false }
      function t:start() self.running = true; return self end
      function t:isRunning() return self.running end
      function t:terminate() self.running = false; self.terminated = true end
      function t:kill9() self.running = false; self.killed = true end
      function t:finish(code, out, err)
        self.running = false
        self.cb(code, out or "", err or "")
      end
      tasks[#tasks + 1] = t
      return t
    end,
  },
  eventtap = {
    event = {
      types = { flagsChanged = "flagsChanged", keyDown = "keyDown", scrollWheel = "scrollWheel" },
      properties = { scrollWheelEventDeltaAxis1 = 11 },
    },
    checkMouseButtons = function() return { left = mouse_buttons.left } end,
    new = function(types, fn)
      local t = { types = types, fn = fn, enabled = false }
      function t:start() self.enabled = true; return self end
      function t:stop() self.enabled = false; return self end
      taps[#taps + 1] = t
      return t
    end,
  },
  mouse = {
    getAbsolutePosition = function() return { x = mouse_pos.x, y = mouse_pos.y } end,
  },
}

local function flags_event(keycode, alt)
  return {
    getFlags = function() return { alt = alt } end,
    getKeyCode = function() return keycode end,
  }
end

local function key_event(keycode, flags)
  return {
    getFlags = function() return flags or {} end,
    getKeyCode = function() return keycode end,
  }
end

local adapter = dofile(ADAPTER .. "init.lua")

local flags_tap, esc_tap
local function find_taps()
  for _, t in ipairs(taps) do
    if t.types[1] == "flagsChanged" then flags_tap = t end
    if t.types[1] == "keyDown" then esc_tap = t end
  end
end

local function press_right_option()
  find_taps()
  flags_tap.fn(flags_event(61, true))
  flags_tap.fn(flags_event(61, false))
end

local function double_tap_left_option()
  find_taps()
  for _ = 1, 2 do
    flags_tap.fn(flags_event(58, true))
    flags_tap.fn(flags_event(58, false))
    advance(0.1)
  end
end

local function press_esc()
  find_taps()
  if not esc_tap or not esc_tap.enabled then
    return false
  end
  return esc_tap.fn(key_event(53, {}))
end

local function set_mouse(x, y)
  mouse_pos.x, mouse_pos.y = x, y
end

-- Click the live canvas: mouseUp with an element id (or nil for hit-test).
local function click(id)
  local c = live_canvas()
  check(c and c.mouse, "mouse callback registered")
  c.mouse(c, "mouseUp", id)
end

local function hover(on)
  local c = live_canvas()
  check(c and c.mouse, "mouse callback registered")
  if on then
    c.mouse(c, "mouseEnter", "background")
  else
    c.mouse(c, "mouseExit", "background")
    advance(0.3)
  end
end

local function find_scroll_tap()
  for _, t in ipairs(taps) do
    if t.types[1] == "scrollWheel" then
      return t
    end
  end
  return nil
end

local function scroll_wheel(delta)
  local t = find_scroll_tap()
  check(t and t.enabled, "scroll tap armed while full overflows")
  return t.fn({ getProperty = function(_, _) return delta end })
end

local function control_ids(c)
  local ids = {}
  for _, el in ipairs(c.elements) do
    if el.id == "copy" or el.id == "close" then
      ids[#ids + 1] = el.id
    end
  end
  return ids
end

local function has_id(c, want)
  for _, id in ipairs(control_ids(c)) do
    if id == want then
      return true
    end
  end
  return false
end

local function write(path, text)
  local f = assert(io.open(path, "w"))
  f:write(text)
  f:close()
end

local function exists(path)
  local f = io.open(path, "r")
  if f then
    f:close()
    return true
  end
  return false
end

local function write_status(kind, state, text, detail)
  write(
    DATA .. "/status.json",
    string.format(
      '{"session":"abc","kind":"%s","state":"%s","text":"%s","detail":"%s","updated_ms":%d,"pid":1}',
      kind, state, text or "", detail or "", math.floor(clock * 1000) + 10
    )
  )
end

-- Canvas contract: [1] background, [2] body text (no title/hint chrome),
-- [3..27] square status-grid cells.
local function body_of(c) return c[2].text end

local scenarios = {}

function scenarios.launch_is_background_only()
  eq(#notifications, 0, "no launch toast")
  eq(#menubars, 0, "no digivoice menubar mark on arm")
  eq(dockicon_hidden, true, "Dock icon hidden on start")
  press_right_option()
  advance(0.5)
  press_right_option()
  advance(0.5)
  tasks[1]:finish(0, "hello\n", "")
  advance(5)
  double_tap_left_option()
  tasks[2]:finish(1, "", "digivoice speak: nothing selected\n")
  advance(5)
  eq(#notifications, 0, "no toast for dict, speak, or errors")
  eq(#menubars, 0, "no digivoice menubar mark during takes")
end

function scenarios.dict_banner_recording_then_done()
  press_right_option()
  local t = tasks[1]
  eq(t.bin, os.getenv("DIGIVOICE_BIN"), "uses DIGIVOICE_BIN")
  eq(table.concat(t.args, " "), "dict --toggle --stop-file " .. DATA .. "/dict.stop", "args")
  local c = live_canvas()
  check(c, "banner canvas shown")
  check(c.shown, "canvas visible")
  eq(c.clickActivating, false, "click must not steal focus")
  eq(c[1].trackMouseUp, true, "background must track mouse-up or click-to-cycle never fires")
  eq(c[1].trackMouseDown, true, "background must track mouse-down or drag never starts")
  eq(c[1].trackMouseEnterExit, true, "background must track hover or controls never show")
  check(c.mouse, "mouse callback registered")
  eq(c[3].type, "rectangle", "status grid is squares, not dots")
  eq(body_of(c), "", "recording shows the grid, no chrome text")
  eq(c.frame.w, 10 * 2 + 18, "empty hugs the grid, no min-width gutter")
  eq(c.frame.x, (1440 - (10 * 2 + 18)) / 2, "top-center x")
  eq(c.frame.y, 16, "top-center y keeps the edge gap")
  eq(#menubars, 0, "no digivoice menubar mark while recording")
  find_taps()
  check(esc_tap.enabled, "Esc tap armed while a take is active")
  press_right_option()
  check(exists(DATA .. "/dict.stop"), "stop-file written")
  write_status("dict", "rewriting", "hello there world", "preset email")
  advance(0.5)
  c = live_canvas()
  eq(body_of(c), "hello there world", "transcript glimpse while processing")
  check(c.frame.w < 380, "peek hugs content instead of the fixed cap")
  write_status("dict", "done", "Hello there, world.", "pasted into the focused app")
  t:finish(0, "Hello there, world.\n", "")
  advance(1)
  c = live_canvas()
  eq(body_of(c), "Hello there, world.", "final text")
  eq(#menubars, 0, "still no digivoice menubar after take")
  advance(5)
  eq(live_canvas(), nil, "peek banner clears a few seconds after done")
  find_taps()
  eq(esc_tap.enabled, false, "Esc tap released")
end

function scenarios.esc_cancels_and_swallows()
  eq(press_esc(), false, "Esc with no take is not swallowed")
  press_right_option()
  advance(0.3)
  eq(press_esc(), true, "Esc during recording is swallowed")
  check(exists(DATA .. "/dict.cancel"), "cancel-file written")
  check(not exists(DATA .. "/dict.stop"), "cancel is not a stop")
  advance(1)
  local cancelling = live_canvas()
  check(cancelling, "banner stays up while cancelling")
  eq(body_of(cancelling), "", "no discard label beside the grid")
  eq(press_esc(), false, "second Esc passes through")
  press_right_option()
  check(not exists(DATA .. "/dict.stop"), "Right Option ignored while cancelling")
  tasks[1]:finish(3, "", "digivoice dict: cancelled\n")
  local c = live_canvas()
  check(c, "banner stays through the linger")
  eq(body_of(c), "", "grid only after cancel")
  eq(#notifications, 0, "no cancel toast")
  advance(3)
  eq(live_canvas(), nil, "banner clears")
end

function scenarios.unwritable_cancel_file_never_kills_the_cli()
  press_right_option()
  os.execute('mkdir -p "' .. DATA .. '/dict.cancel/blocker"')
  eq(press_esc(), false, "Esc is not swallowed when the cancel-file cannot be written")
  eq(tasks[1].killed, false, "CLI not killed (its recorder would be orphaned)")
  eq(tasks[1].terminated, nil, "CLI not terminated (that would paste)")
  eq(body_of(live_canvas()), "", "still recording, grid only")
end

function scenarios.esc_cancels_during_processing()
  press_right_option()
  press_right_option()
  write_status("dict", "transcribing", "", "")
  advance(0.2)
  eq(press_esc(), true, "Esc while transcribing cancels")
  check(exists(DATA .. "/dict.cancel"), "cancel-file written")
end

function scenarios.esc_passes_through_once_pasting()
  press_right_option()
  press_right_option()
  write_status("dict", "pasting", "hello", "")
  advance(0.2)
  eq(press_esc(), false, "Esc while pasting is the app's own Esc")
  check(not exists(DATA .. "/dict.cancel"), "no cancel-file")
end

function scenarios.speak_is_not_esc_cancelled()
  double_tap_left_option()
  eq(table.concat(tasks[1].args, " "), "speak --selection", "speak args")
  write_status("speak", "speaking", "selected reply text", "")
  advance(0.5)
  local c = live_canvas()
  eq(body_of(c), "selected reply text", "selected text shown, no chrome")
  eq(press_esc(), false, "Esc does not swallow during speech")
  tasks[1]:finish(0, "selected reply text\n", "")
  advance(5)
  eq(live_canvas(), nil, "cleared")
end

function scenarios.speak_failure_goes_to_the_banner()
  double_tap_left_option()
  tasks[1]:finish(1, "", "digivoice speak: nothing selected: select text first\n")
  advance(1)
  local c = live_canvas()
  check(c, "failure stays on the banner")
  eq(body_of(c), "", "failure stays on the grid, no status sentence")
  eq(#notifications, 0, "no toast")
end

function scenarios.error_and_empty_exit_states()
  press_right_option()
  press_right_option()
  tasks[1]:finish(1, "", "digivoice dict: whisper-cli failed (boom)\n")
  advance(1)
  local err = live_canvas()
  check(err, "error banner stays")
  eq(body_of(err), "", "error detail is not a label")
  advance(5)
  press_right_option()
  press_right_option()
  write_status("dict", "empty", "", "nothing recognized")
  tasks[2]:finish(1, "", "digivoice dict: whisper-cli returned no text; take discarded\n")
  advance(1)
  local c = live_canvas()
  check(c, "empty banner stays")
  eq(body_of(c), "", "empty take is grid only")
end

function scenarios.stale_status_is_ignored()
  write_status("dict", "done", "OLD TEXT", "")
  clock = clock + 10
  press_right_option()
  local c = live_canvas()
  eq(body_of(c), "", "stale done must not show text")
end

function scenarios.position_setting()
  write(DATA .. "/settings.json", '{"banner_position": "bottom-right", "live_banner": true}')
  press_right_option()
  local c = live_canvas()
  eq(c.frame.x, 1440 - c.frame.w - 16, "bottom-right x keeps the edge gap")
  eq(c.frame.y, 900 - c.frame.h - 16, "bottom-right y keeps the edge gap")
end

function scenarios.middle_anchors()
  write(DATA .. "/settings.json", '{"banner_position": "middle-left", "live_banner": true}')
  press_right_option()
  local c = live_canvas()
  eq(c.frame.x, 16, "middle-left x keeps the edge gap")
  eq(c.frame.y, (900 - c.frame.h) / 2, "middle-left is vertically centered")
end

function scenarios.bad_position_falls_back()
  write(DATA .. "/settings.json", '{"banner_position": "nowhere"}')
  press_right_option()
  eq(live_canvas().frame.x, (1440 - (10 * 2 + 18)) / 2, "default top-center")
end

function scenarios.banner_disabled()
  write(DATA .. "/settings.json", '{"live_banner": false}')
  press_right_option()
  eq(live_canvas(), nil, "no canvas when disabled")
  eq(#menubars, 0, "no digivoice menubar when banner off")
  eq(press_esc(), true, "Esc still cancels")
  check(exists(DATA .. "/dict.cancel"), "cancel-file written")
  tasks[1]:finish(3, "", "")
  eq(live_canvas(), nil, "still no canvas")
  eq(#notifications, 0, "still no toast")
end

function scenarios.animations_toggle()
  local function alphas(c)
    local out = {}
    for i = 3, 27 do out[#out + 1] = c[i].fillColor.alpha end
    return table.concat(out, ",")
  end
  press_right_option()
  local c = live_canvas()
  eq(c[3].type, "rectangle", "grid cells are squares")
  local first = alphas(c)
  advance(0.3)
  check(alphas(live_canvas()) ~= first, "grid animates")
  tasks[1]:finish(3, "", "")
  advance(5)
  write(DATA .. "/settings.json", '{"banner_animations": false}')
  press_right_option()
  c = live_canvas()
  first = alphas(c)
  advance(0.3)
  eq(alphas(live_canvas()), first, "grid is a still frame")
end

function scenarios.click_cycles_density()
  local long = string.rep("alpha beta gamma delta ", 30)
  press_right_option()
  write_status("dict", "rewriting", long, "")
  advance(3)
  local c = live_canvas()
  check(c.frame.w < 380, "peek hugs instead of the fixed cap")
  check(body_of(c):find("…", 1, true), "glimpse is clipped")
  local peek_w = c.frame.w
  c.mouse(c, "mouseUp") -- peek → full
  advance(3)
  c = live_canvas()
  check(c.frame.w > peek_w, "full widens past the peek hug")
  check(c.frame.w <= 580, "full respects the expanded cap")
  check(#body_of(c) > 0, "full shows more text")
  c.mouse(c, "mouseUp") -- full → mini
  advance(0.2)
  c = live_canvas()
  eq(c.frame.w, 10 * 2 + 18, "mini hugs the grid")
  eq(body_of(c), "", "mini is grid only")
  c.mouse(c, "mouseUp") -- mini → peek
  advance(3)
  eq(live_canvas().frame.w, peek_w, "back to the same peek hug")
end

function scenarios.density_mini_setting_is_grid_only()
  write(DATA .. "/settings.json", '{"banner_density": "mini"}')
  press_right_option()
  local c = live_canvas()
  eq(c.frame.w, 10 * 2 + 18, "mini hugs the grid")
  eq(body_of(c), "", "mini shows no text")
end

function scenarios.density_full_stays_after_done()
  write(DATA .. "/settings.json", '{"banner_density": "full"}')
  press_right_option()
  press_right_option()
  write_status("dict", "done", "final words", "")
  tasks[1]:finish(0, "final words\n", "")
  advance(1)
  eq(body_of(live_canvas()), "final words", "final text shown")
  advance(8)
  check(live_canvas(), "full stays: no auto-hide")
  eq(body_of(live_canvas()), "final words", "text kept")
end

function scenarios.bad_density_falls_back_to_peek()
  write(DATA .. "/settings.json", '{"banner_density": "huge"}')
  press_right_option()
  eq(live_canvas().frame.w, 10 * 2 + 18, "empty peek hugs the grid like mini")
end

function scenarios.home_banner_stands_by_without_blocking_hotkeys()
  eq(adapter.ensure_banner(), "shown", "standby banner shown")
  check(live_canvas(), "canvas up")
  eq(#tasks, 0, "standby starts no CLI")
  eq(#menubars, 0, "standby does not touch the menubar")
  eq(adapter.ensure_banner(), "visible", "second call sees the canvas")
  press_right_option()
  eq(#tasks, 1, "dict still starts over standby")
  eq(table.concat(tasks[1].args, " "), "dict --toggle --stop-file " .. DATA .. "/dict.stop", "dict args")
  tasks[1]:finish(0, "hello\n", "")
  advance(5)
  eq(adapter.ensure_banner(), "shown", "banner returns after the take")
  double_tap_left_option()
  eq(#tasks, 2, "speak still starts over standby")
  eq(table.concat(tasks[2].args, " "), "speak --selection", "speak args")
end

function scenarios.cli_missing_is_reported()
  hs.task.new = function() return nil end
  press_right_option()
  eq(live_canvas(), nil, "no banner without a task")
  eq(#notifications, 0, "no toast")
end

local function button_frames(c)
  local out = {}
  for _, el in ipairs(c.elements) do
    if (el.id == "copy" or el.id == "close") and el.type == "rectangle" and el.trackMouseUp then
      out[#out + 1] = el
    end
  end
  return out
end

local function button_frame(c, want)
  for _, el in ipairs(button_frames(c)) do
    if el.id == want then
      return el.frame
    end
  end
  return nil
end

function scenarios.hidden_by_default()
  eq(live_canvas(), nil, "no banner at launch without a take or flag")
  eq(#tasks, 0, "nothing spawned")
end

function scenarios.spawn_flag_preview()
  write(DATA .. "/banner.show", '{"visible": true, "text": "preview words here"}')
  advance(1.2)
  local c = live_canvas()
  check(c, "preview spawns from the flag")
  eq(#tasks, 0, "no dictation needed to show")
  advance(1)
  eq(body_of(live_canvas()), "preview words here", "flag text shown")
  find_taps()
  check(esc_tap.enabled, "Esc armed for the preview")
  eq(press_esc(), true, "Esc hides the preview")
  eq(live_canvas(), nil, "preview hidden instantly")
  local f = io.open(DATA .. "/banner.show", "r")
  local flag = f:read("*a")
  f:close()
  check(flag:find("false", 1, true), "flag cleared so it stays hidden")
end

function scenarios.hover_controls_row()
  press_right_option()
  write_status("dict", "rewriting", "hover me", "")
  advance(1)
  eq(#button_frames(live_canvas()), 0, "no controls until hover")
  local plain = live_canvas()
  local face_h, face_w = plain[1].frame.h, plain[1].frame.w
  eq(plain.frame.h, face_h, "no gutter without hover")
  hover(true)
  local c = live_canvas()
  local copy, close = button_frame(c, "copy"), button_frame(c, "close")
  check(copy and close, "hover shows icon-only copy + close")
  eq(copy.y, close.y, "wider densities row the controls")
  eq(close.x, copy.x + 18 + 4, "copy sits left of close")
  eq(copy.x + 18 + 4 + 18, c.frame.w, "row is right-aligned under the banner")
  eq(copy.w, 18, "icon squares match the grid")
  -- Single-canvas chrome (mock .float-root): banner face stays box.h, the
  -- control gutter below is transparent canvas, not a stretched fill.
  eq(c[1].frame.h, face_h, "banner face keeps box.h on hover")
  eq(c[1].frame.w, face_w, "banner face keeps box.w on hover")
  eq(copy.y, face_h + 4, "controls sit below with the CTRL_GAP margin")
  eq(c.frame.h, face_h + 4 + 18, "canvas grows by exactly the row gutter")
  -- Equal padding: the grid hugs the top-left corner.
  check(math.abs(c[3].frame.x - 10) < 3 and math.abs(c[3].frame.y - 10) < 3, "grid top-left with even pad")
  check(math.abs(plain[2].frame.y - (10 + (18 - 11) / 2)) < 0.001, "first line centers on the icon row")
  local rounded, round_cap = false, false
  for _, el in ipairs(c.elements) do
    if el.id == "copy" and el.roundedRectRadii then
      rounded = true
    end
    if el.id == "close" and el.strokeCap == "round" then
      round_cap = true
    end
  end
  check(rounded, "copy uses the DigiChat rounded sheets")
  check(round_cap, "close uses the DigiChat round-cap mark")
  click("copy")
  local clip = io.open(os.getenv("DIGIVOICE_PBCOPY_FILE"), "r")
  eq(clip:read("*a"), "hover me", "copy puts the banner text on the clipboard")
  clip:close()
  check(live_canvas(), "copy does not dismiss")
  hover(false)
  eq(#button_frames(live_canvas()), 0, "controls leave with the cursor")
end

function scenarios.hover_controls_stack()
  write(DATA .. "/settings.json", '{"banner_density": "mini"}')
  press_right_option()
  advance(0.2)
  hover(true)
  local c = live_canvas()
  local copy, close = button_frame(c, "copy"), button_frame(c, "close")
  check(copy and close, "mini shows both controls")
  eq(copy.x, close.x, "mini stacks the controls")
  check(close.y > copy.y, "close sits below copy")
  eq(copy.x, (c.frame.w - 18) / 2, "stack is centered under the banner")
  hover(false)
end

function scenarios.close_is_instant_hide()
  press_right_option()
  write_status("dict", "rewriting", "bye for now", "")
  advance(1)
  hover(true)
  click("close")
  eq(live_canvas(), nil, "close hides instantly, no reverse animation")
  check(tasks[1]:isRunning(), "the take keeps running silently")
  advance(5)
  eq(live_canvas(), nil, "stays hidden")
  tasks[1]:finish(0, "bye for now\n", "")
  advance(5)
  eq(live_canvas(), nil, "hidden takes never pop back up")
end

function scenarios.drag_snaps_and_persists()
  press_right_option()
  advance(0.2)
  local c = live_canvas()
  set_mouse(c.frame.x + 10, c.frame.y + 10)
  c.mouse(c, "mouseDown", "background")
  mouse_buttons.left = true
  advance(0.15)
  set_mouse(30, 42)
  advance(0.3)
  mouse_buttons.left = false
  advance(0.3)
  c = live_canvas()
  eq(c.frame.x, 16, "snapped to the tl anchor x")
  eq(c.frame.y, 16, "snapped to the tl anchor y")
  local f = io.open(DATA .. "/banner_pos.json", "r")
  check(f, "position persisted")
  local saved = f:read("*a")
  f:close()
  check(saved:find("tl", 1, true), "anchor persisted")
  tasks[1]:finish(0, "x\n", "")
  advance(6)
  eq(live_canvas(), nil, "cleared")
  press_right_option()
  advance(0.2)
  c = live_canvas()
  eq(c.frame.x, 16, "next take reuses the persisted x")
  eq(c.frame.y, 16, "next take reuses the persisted y")
end

function scenarios.instant_text_no_typewriter()
  local long = string.rep("word ", 60)
  press_right_option()
  write_status("dict", "rewriting", long, "")
  advance(0.2)
  local peek = body_of(live_canvas())
  check(#peek > 20, "peek shows the glimpse at once")
  check(peek:find("word", 1, true), "transcript is present immediately")
  check(peek:find("…", 1, true), "peek still clips with an ellipsis")
  click(nil) -- peek → full
  local shown = body_of(live_canvas())
  check(#shown > #peek, "full shows more than the peek glimpse at once")
  check(shown:find("word", 1, true), "same transcript, shown in full window")
  advance(0.2)
  eq(body_of(live_canvas()), shown, "text does not keep revealing")
end

function scenarios.full_scroll_caps_and_wheels()
  local rows = {}
  for i = 1, 30 do
    rows[#rows + 1] = "line " .. i .. " with some words here"
  end
  write(DATA .. "/settings.json", '{"banner_density": "full"}')
  press_right_option()
  write_status("dict", "rewriting", table.concat(rows, "\n"), "")
  advance(10)
  local c = live_canvas()
  check(c.frame.h <= 450, "full caps near half the viewport height")
  local first = body_of(c)
  check(first:find("line 1", 1, true), "window starts at the top")
  check(find_scroll_tap(), "wheel armed while full overflows")
  eq(scroll_wheel(-1), true, "wheel down scrolls")
  local moved = body_of(live_canvas())
  check(moved ~= first, "the line window moves")
  local top = moved:match("^[^\n]*") or ""
  check(top:find("line 4", 1, true), "top lines scrolled away")
  scroll_wheel(1)
  eq(body_of(live_canvas()), first, "wheel up returns to the top")
end

function scenarios.reanchor_center()
  write(DATA .. "/settings.json", '{"banner_position": "center", "live_banner": true}')
  press_right_option()
  advance(0.2)
  local c = live_canvas()
  local cx = c.frame.x + c.frame.w / 2
  local cy = c.frame.y + c.frame.h / 2
  eq(cx, 720, "starts page-centered")
  write_status("dict", "rewriting", "center pin keeps center on expand", "")
  advance(1)
  click(nil) -- peek → full
  c = live_canvas()
  eq(c.frame.x + c.frame.w / 2, cx, "center x kept while growing outward")
  eq(c.frame.y + c.frame.h / 2, cy, "center y kept while growing outward")
end

function scenarios.theme_chrome_dark()
  press_right_option()
  advance(0.2)
  local c = live_canvas()
  local bg = c[1].fillColor
  check(math.abs(bg.red) < 0.002 and math.abs(bg.green) < 0.002 and math.abs(bg.blue) < 0.002, "remock dark ground")
  local ink = c[2].textColor
  check(math.abs(ink.red - 0xED / 255) < 0.002, "remock dark ink")
  eq(c[3].fillColor.red, 0.94, "recording red stays across themes")
end

local run = scenarios[scenario]
if not run then
  fail("unknown scenario")
end
run()
print("PASS " .. scenario)
