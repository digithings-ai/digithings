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
    local ok, err = pcall(nxt.fn)
    if not ok then
      -- hs.timer stops a repeating callback after an error (continueOnError is false).
      nxt.live = false
      nxt.err = err
    end
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
  -- Real hs.canvas[i] is a proxy. fillColor writes through. Any other attribute
  -- (including `phase`) raises "unrecognized", which stops the frame timer.
  local function element_view(el)
    return setmetatable({}, {
      __index = el,
      __newindex = function(_, key, value)
        if key == "fillColor" then
          el[key] = value
          return
        end
        error("attribute name " .. tostring(key) .. " unrecognized", 2)
      end,
    })
  end
  setmetatable(c, {
    __index = function(t, k)
      if type(k) == "number" then
        local el = rawget(t, "elements")[k]
        if el then
          return element_view(el)
        end
        return nil
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
    getType = function() return "flagsChanged" end,
  }
end

local function key_event(keycode, flags)
  return {
    getFlags = function() return flags or {} end,
    getKeyCode = function() return keycode end,
    getType = function() return "keyDown" end,
  }
end

local adapter = dofile(ADAPTER .. "init.lua")
local launches = {}
adapter.launch_tui = function(action)
  launches[#launches + 1] = action
end

local flags_tap, esc_tap
local function find_taps()
  for _, t in ipairs(taps) do
    if t.types[1] == "flagsChanged" then
      flags_tap = t
      -- The hotkey tap also listens for keyDown. That is the cancel key.
      if t.types[2] == "keyDown" then
        esc_tap = t
      end
    end
    if t.types[1] == "keyDown" then
      esc_tap = t
    end
  end
end

local function press_chord(keycode, flags)
  find_taps()
  return flags_tap.fn(key_event(keycode, flags))
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
    if el.id == "pin" then
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

-- Canvas contract: [1] background (phase on the element), [2..26] status-grid cells.
local function phase_of(c) return c[1].phase or "" end

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
  eq(c.clickActivating, false, "the overlay itself does not take focus")
  eq(c[1].trackMouseUp, true, "background must track mouse-up or the click never fires")
  eq(c[1].trackMouseDown, true, "background must track mouse-down or drag never starts")
  eq(c[1].trackMouseEnterExit, false, "no hover controls")
  check(c.mouse, "mouse callback registered")
  eq(c[2].type, "rectangle", "status grid is squares, not dots")
  eq(phase_of(c), "recording", "recording icon")
  eq(c.frame.w, 38, "icon only")
  eq(c.frame.h, 38, "icon only")
  eq(c.frame.x, (1440 - c.frame.w) / 2, "top-center x")
  eq(c.frame.y, 16, "top-center y keeps the edge gap")
  eq(#menubars, 0, "no digivoice menubar mark while recording")
  find_taps()
  check(esc_tap.enabled, "Esc tap armed while a take is active")
  press_right_option()
  check(exists(DATA .. "/dict.stop"), "stop-file written")
  write_status("dict", "rewriting", "hello there world", "preset email")
  advance(0.5)
  c = live_canvas()
  eq(phase_of(c), "processing", "retract shows the processing icon")
  check(not phase_of(c):find("hello", 1, true), "transcript stays off the banner")
  write_status("dict", "done", "Hello there, world.", "pasted into the focused app")
  t:finish(0, "Hello there, world.\n", "")
  advance(0.2)
  eq(live_canvas(), nil, "retract hides when the take is done")
  eq(#menubars, 0, "still no digivoice menubar after take")
  find_taps()
  eq(press_esc(), false, "Esc passes through after the take")
end

function scenarios.esc_cancels_and_swallows()
  eq(press_esc(), false, "Esc with no take is not swallowed")
  press_right_option()
  advance(0.3)
  eq(press_esc(), true, "Esc during recording is swallowed")
  check(exists(DATA .. "/dict.cancel"), "cancel-file written")
  check(not exists(DATA .. "/dict.stop"), "cancel is not a stop")
  advance(1)
  eq(live_canvas(), nil, "cancel retracts the icon")
  eq(press_esc(), false, "second Esc passes through")
  press_right_option()
  check(not exists(DATA .. "/dict.stop"), "Right Option ignored while cancelling")
  tasks[1]:finish(3, "", "digivoice dict: cancelled\n")
  eq(live_canvas(), nil, "a finished cancel stays hidden")
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
  eq(phase_of(live_canvas()), "recording", "still recording")
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
  eq(phase_of(c), "processing", "speech is the processing icon")
  eq(press_esc(), false, "Esc does not swallow during speech")
  click(nil)
  eq(launches[#launches], "open", "click opens the terminal")
  eq(phase_of(live_canvas()), "processing", "click keeps the processing icon")
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
  eq(phase_of(c), "error", "a failure shows the error icon")
  eq(#notifications, 0, "no toast")
end

function scenarios.error_and_empty_exit_states()
  press_right_option()
  press_right_option()
  tasks[1]:finish(1, "", "digivoice dict: whisper-cli failed (boom)\n")
  advance(1)
  local err = live_canvas()
  check(err, "error banner stays")
  eq(phase_of(err), "error", "error is an icon, not the detail")
  advance(5)
  press_right_option()
  press_right_option()
  write_status("dict", "empty", "", "nothing recognized")
  tasks[2]:finish(1, "", "digivoice dict: whisper-cli returned no text; take discarded\n")
  advance(1)
  eq(live_canvas(), nil, "nothing to show retracts")
end

function scenarios.stale_status_is_ignored()
  write_status("dict", "done", "OLD TEXT", "")
  clock = clock + 10
  press_right_option()
  local c = live_canvas()
  eq(phase_of(c), "recording", "stale transcript is not the banner")
  check(not phase_of(c):find("OLD", 1, true), "old text stays off the banner")
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
  local c = live_canvas()
  eq(c.frame.x, (1440 - c.frame.w) / 2, "default top-center")
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
    for i = 2, 26 do out[#out + 1] = c[i].fillColor.alpha end
    return table.concat(out, ",")
  end
  press_right_option()
  local c = live_canvas()
  eq(c[2].type, "rectangle", "grid cells are squares")
  local first = alphas(c)
  advance(0.2)
  local mid = alphas(live_canvas())
  check(mid ~= first, "recording bars move")
  advance(0.2)
  check(alphas(live_canvas()) ~= mid, "recording bars keep moving")
  tasks[1]:finish(3, "", "")
  advance(0.2)
  write(DATA .. "/settings.json", '{"banner_animations": false}')
  press_right_option()
  write_status("dict", "rewriting", "", "")
  advance(0.2)
  c = live_canvas()
  first = alphas(c)
  advance(0.4)
  eq(alphas(live_canvas()), first, "animations off holds a still frame")
end

function scenarios.click_focuses_or_opens()
  local long = string.rep("alpha beta gamma delta ", 30)
  press_right_option()
  write_status("dict", "rewriting", long, "")
  advance(0.3)
  local c = live_canvas()
  eq(phase_of(c), "processing", "processing icon, not the transcript")
  check(c.frame.w < 180, "status banner stays small")
  local width = c.frame.w
  click(nil)
  eq(launches[#launches], "open", "click opens the terminal")
  c = live_canvas()
  eq(c.frame.w, width, "click does not resize the icon")
  eq(phase_of(c), "processing", "click keeps the processing icon")
  check(not phase_of(c):find("alpha", 1, true), "transcript never lands on the banner")
  write(DATA .. "/tui.pid", "4242\n")
  click(nil)
  eq(launches[#launches], "focus", "click focuses the open terminal")
  eq(#launches, 2, "a second click does not open another terminal")
end

function scenarios.density_retract_setting_is_grid_only()
  write(DATA .. "/settings.json", '{"banner_density": "retract"}')
  press_right_option()
  local c = live_canvas()
  eq(phase_of(c), "recording", "retract shows the recording icon")
  check(c.frame.w < 180, "retract stays a small status banner")
end

function scenarios.density_full_stays_after_done()
  write(DATA .. "/settings.json", '{"banner_pinned": true}')
  press_right_option()
  press_right_option()
  write_status("dict", "done", "final words", "")
  tasks[1]:finish(0, "final words\n", "")
  advance(0.2)
  check(live_canvas(), "a pin keeps the icon up")
  advance(2)
  check(live_canvas(), "a pin does not auto-hide")
  eq(phase_of(live_canvas()), "idle", "done settles to the idle icon")
end

function scenarios.bad_density_falls_back_to_retract()
  write(DATA .. "/settings.json", '{"banner_density": "huge"}')
  press_right_option()
  eq(phase_of(live_canvas()), "recording", "unknown density still shows status")
  check(live_canvas().frame.w < 180, "unknown density stays compact")
end

function scenarios.home_banner_stands_by_without_blocking_hotkeys()
  eq(adapter.ensure_banner(), "armed", "launch does not draw the banner")
  eq(live_canvas(), nil, "no canvas until a take")
  eq(#tasks, 0, "arming starts no CLI")
  eq(#menubars, 0, "arming does not touch the menubar")
  eq(adapter.ensure_banner(), "armed", "second call still stays hidden")
  press_right_option()
  eq(#tasks, 1, "dict still starts")
  check(live_canvas(), "the take shows the banner")
  eq(phase_of(live_canvas()), "recording", "recording status")
  eq(table.concat(tasks[1].args, " "), "dict --toggle --stop-file " .. DATA .. "/dict.stop", "dict args")
  tasks[1]:finish(0, "hello\n", "")
  advance(5)
  eq(live_canvas(), nil, "retract hides after the take")
  eq(adapter.ensure_banner(), "armed", "it does not come back on its own")
  double_tap_left_option()
  eq(#tasks, 2, "speak still starts")
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
    if el.id == "pin" and el.type == "rectangle" and el.trackMouseUp then
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
  write(DATA .. "/settings.json", '{"banner_density": "full"}')
  write(DATA .. "/banner.show", '{"visible": true, "text": "preview words here"}')
  advance(1.2)
  local c = live_canvas()
  check(c, "preview spawns from the flag")
  eq(#tasks, 0, "no dictation needed to show")
  advance(1)
  eq(phase_of(live_canvas()), "recording", "preview is a status, not the flag text")
  find_taps()
  check(esc_tap.enabled, "Esc armed for the preview")
  eq(press_esc(), true, "Esc hides the preview")
  eq(live_canvas(), nil, "preview hidden instantly")
  local f = io.open(DATA .. "/banner.show", "r")
  local flag = f:read("*a")
  f:close()
  check(flag:find("false", 1, true), "flag cleared so it stays hidden")
end

function scenarios.pending_flag_hides_the_icon()
  press_right_option()
  check(live_canvas(), "recording shows before the flag")
  write(DATA .. "/banner.show", '{"visible": true, "pending": true, "text": ""}')
  advance(0.3)
  eq(live_canvas(), nil, "a pending flag retracts the icon")
  write(DATA .. "/banner.show", '{"visible": false, "pending": false}')
  advance(0.3)
  check(live_canvas(), "recording returns when pending clears")
  tasks[1]:finish(0, "done\n", "")
  advance(0.3)
  eq(live_canvas(), nil, "take end stays hidden")
  write(DATA .. "/banner.show", '{"visible": true, "pending": true}')
  advance(1.2)
  eq(live_canvas(), nil, "pending does not spawn a preview")
end

function scenarios.hover_controls_row()
  press_right_option()
  write_status("dict", "rewriting", "hover me", "")
  advance(0.2)
  local plain = live_canvas()
  eq(#button_frames(plain), 0, "no pin on the banner")
  eq(plain.frame.h, plain[1].frame.h, "no control gutter")
  hover(true)
  local c = live_canvas()
  eq(#button_frames(c), 0, "hover adds no controls")
  eq(c.frame.h, plain.frame.h, "hover does not grow the icon")
  check(math.abs(c[2].frame.x - 10) < 3 and math.abs(c[2].frame.y - 10) < 3, "grid top-left with even pad")
  eq(phase_of(c), "processing", "hover does not reveal the transcript")
  click(nil)
  check(live_canvas(), "click does not dismiss a live take")
  local saved = io.open(DATA .. "/settings.json", "r")
  if saved then
    local settings = saved:read("*a")
    saved:close()
    check(not settings:find('"banner_pinned"', 1, true), "click does not write a pin")
  end
end

function scenarios.hover_controls_stack()
  write(DATA .. "/settings.json", '{"banner_density": "retract"}')
  press_right_option()
  advance(0.2)
  local c = live_canvas()
  eq(#button_frames(c), 0, "retract has no pin")
  eq(#c.elements, 26, "background plus the 25 icon cells")
end

function scenarios.close_is_instant_hide()
  press_right_option()
  write_status("dict", "rewriting", "bye for now", "")
  advance(0.2)
  click(nil)
  check(tasks[1]:isRunning(), "click does not stop the take")
  check(live_canvas(), "click keeps a live take up")
  eq(launches[#launches], "open", "click opens the terminal")
  write(DATA .. "/tui.pid", "99\n")
  click(nil)
  eq(launches[#launches], "focus", "the next click focuses")
  eq(#launches, 2, "focus does not open a second terminal")
  check(tasks[1]:isRunning(), "the take keeps running")
  tasks[1]:finish(0, "bye for now\n", "")
  advance(0.2)
  eq(live_canvas(), nil, "retract hides after the take")
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
  write(DATA .. "/settings.json", '{"banner_density": "full"}')
  press_right_option()
  write_status("dict", "rewriting", long, "")
  advance(0.2)
  eq(phase_of(live_canvas()), "processing", "the icon replaces the transcript")
  check(not phase_of(live_canvas()):find("word", 1, true), "transcript stays off the banner")
  advance(0.2)
  eq(phase_of(live_canvas()), "processing", "the icon does not type on")
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
  check(c.frame.h < 80, "status banner does not grow with the transcript")
  eq(phase_of(c), "processing", "one processing icon")
  eq(find_scroll_tap(), nil, "nothing to scroll")
end

function scenarios.reanchor_center()
  write(DATA .. "/settings.json", '{"banner_position": "center", "live_banner": true}')
  press_right_option()
  advance(0.2)
  local c = live_canvas()
  local cx = c.frame.x + c.frame.w / 2
  local cy = c.frame.y + c.frame.h / 2
  eq(cx, 720, "starts page-centered")
  write_status("dict", "error", "center pin keeps center on expand", "boom")
  advance(0.3)
  click(nil)
  c = live_canvas()
  eq(phase_of(c), "error", "error is the icon")
  eq(c.frame.x + c.frame.w / 2, cx, "center x stays when the icon changes")
end

function scenarios.theme_chrome_dark()
  press_right_option()
  advance(0.2)
  local c = live_canvas()
  local bg = c[1].fillColor
  check(math.abs(bg.red) < 0.002 and math.abs(bg.green) < 0.002 and math.abs(bg.blue) < 0.002, "remock dark ground")
  check(c[2].text == nil, "no status word")
  eq(c[2].fillColor.red, 0.94, "recording red stays across themes")
end

function scenarios.pinned_banner_shows_at_launch()
  write(DATA .. "/settings.json", '{"banner_pinned": true}')
  eq(adapter.ensure_banner(), "shown", "a pin draws the banner")
  check(live_canvas(), "canvas up")
  eq(phase_of(live_canvas()), "idle", "a pin shows the idle icon")
  eq(#tasks, 0, "pin starts no CLI")
  click(nil)
  check(live_canvas(), "click does not hide a pinned icon")
  eq(launches[#launches], "open", "click opens the terminal")
  local f = io.open(DATA .. "/settings.json", "r")
  local text = f:read("*a")
  f:close()
  check(text:find("true", 1, true), "the pin setting stays in the terminal UI")
end

function scenarios.remapped_hotkeys_replace_the_defaults()
  write(DATA .. "/settings.json", '{"dictation":"ctrl+shift+space","speak":"ctrl+shift+s","cancel":"ctrl+shift+x"}')
  press_right_option()
  eq(#tasks, 0, "Right Option is not dictation after a remap")
  double_tap_left_option()
  eq(#tasks, 0, "Left Option is not speak after a remap")
  eq(press_esc(), false, "plain Esc is not cancel after a remap")
  eq(press_chord(49, { ctrl = true, shift = true }), true, "ctrl+shift+space is swallowed")
  eq(#tasks, 1, "ctrl+shift+space starts dictation")
  eq(tasks[1].args[1], "dict", "dictation command")
  eq(press_esc(), false, "Esc does not cancel the remapped take")
  check(not exists(DATA .. "/dict.cancel"), "Esc wrote no cancel-file")
  eq(press_chord(7, { ctrl = true, shift = true }), true, "ctrl+shift+x cancels")
  check(exists(DATA .. "/dict.cancel"), "cancel-file from the saved bind")
  tasks[1]:finish(3, "", "")
  advance(0.2)
  press_chord(1, { ctrl = true, shift = true })
  eq(#tasks, 2, "ctrl+shift+s speaks")
  eq(tasks[2].args[1], "speak", "speak command")
end

function scenarios.bad_binding_keeps_the_previous_and_rereads()
  local lines = {}
  local real_print = print
  print = function(msg)
    lines[#lines + 1] = tostring(msg)
    real_print(msg)
  end
  write(DATA .. "/settings.json", '{"dictation":"!!!"}')
  press_right_option()
  eq(#tasks, 1, "bad dictation keeps Right Option")
  local saw = false
  for _, line in ipairs(lines) do
    if line:find("!!!", 1, true) and line:find("Right Option", 1, true) then
      saw = true
    end
  end
  check(saw, "warning names the bad binding and the one kept")
  press_right_option()
  check(exists(DATA .. "/dict.stop"), "the tap still accepts the next key")
  tasks[1]:finish(0, "ok\n", "")
  advance(0.2)
  write(DATA .. "/settings.json", '{"dictation":"ctrl+shift+space"}')
  press_right_option()
  eq(#tasks, 1, "a saved remap drops Right Option on the next key")
  press_chord(49, { ctrl = true, shift = true })
  eq(#tasks, 2, "the next key uses the new bind without a reload")
end

function scenarios.hotkey_tap_survives_a_bad_event()
  find_taps()
  flags_tap.fn({
    getType = function() error("bad event") end,
    getKeyCode = function() return 0 end,
    getFlags = function() return {} end,
  })
  press_right_option()
  eq(#tasks, 1, "the tap still accepts the next key")
end

function scenarios.reload_reads_saved_hotkeys()
  write(DATA .. "/settings.json", '{"dictation":"ctrl+shift+space","speak":"Double-tap Left Option","cancel":"Esc"}')
  adapter.start()
  press_right_option()
  eq(#tasks, 0, "reload dropped Right Option")
  press_chord(49, { ctrl = true, shift = true })
  eq(#tasks, 1, "reload armed the saved dictation bind")
  eq(tasks[1].args[1], "dict", "still dictation")
end

function scenarios.speak_hotkey_stops_a_readout_without_starting_another()
  double_tap_left_option()
  eq(#tasks, 1, "first tap speaks")
  double_tap_left_option()
  eq(#tasks, 1, "second tap does not start another readout")
  check(exists(DATA .. "/speak.stop"), "stop file asks the player to die")
  eq(tasks[1].terminated, nil, "the CLI is not terminated")
  eq(tasks[1].killed, false, "the CLI is not killed")
  eq(press_esc(), false, "Esc still does not cancel speech")
  check(not exists(DATA .. "/dict.cancel"), "Esc wrote no dict cancel-file")
  tasks[1]:finish(3, "", "digivoice speak: stopped\n")
  advance(0.2)
  double_tap_left_option()
  eq(#tasks, 2, "a tap with nothing playing speaks again")
  check(not exists(DATA .. "/speak.stop"), "a new readout clears the stop file")
end

function scenarios.dict_hotkey_stops_the_readout_before_listening()
  double_tap_left_option()
  press_right_option()
  eq(#tasks, 1, "dictation waits while the readout is still playing")
  check(exists(DATA .. "/speak.stop"), "the readout is told to stop")
  check(not exists(DATA .. "/dict.stop"), "listening has not started")
  tasks[1]:finish(3, "", "digivoice speak: stopped\n")
  advance(0.1)
  eq(#tasks, 2, "dictation starts after the readout exits")
  eq(tasks[2].args[1], "dict", "the next task is dictation")
end

local run = scenarios[scenario]
if not run then
  fail("unknown scenario")
end
run()
print("PASS " .. scenario)
