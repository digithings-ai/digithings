-- Drives digivoice/hammerspoon/init.lua against a fake `hs` so the banner, Esc cancel,
-- and notification rules can be checked without a Mac.
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

hs = {
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
    event = { types = { flagsChanged = "flagsChanged", keyDown = "keyDown" } },
    new = function(types, fn)
      local t = { types = types, fn = fn, enabled = false }
      function t:start() self.enabled = true; return self end
      function t:stop() self.enabled = false; return self end
      taps[#taps + 1] = t
      return t
    end,
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

local function title_of(c) return c[2].text end
local function body_of(c) return c[4].text end

local scenarios = {}

function scenarios.launch_notice_is_the_only_toast()
  eq(#notifications, 1, "one launch toast")
  local text = notifications[1].informativeText
  check(text:find("Esc", 1, true), "lists Esc cancel")
  check(text:find("Right Option", 1, true), "lists dictate")
  check(text:find("Left Option", 1, true), "lists speak")
  check(text:find("cli: " .. os.getenv("DIGIVOICE_BIN"), 1, true), "shows the CLI path")
  press_right_option()
  advance(0.5)
  press_right_option()
  advance(0.5)
  tasks[1]:finish(0, "hello\n", "")
  advance(5)
  double_tap_left_option()
  tasks[2]:finish(1, "", "digivoice speak: nothing selected\n")
  advance(5)
  eq(#notifications, 1, "no toast for dict, speak, or errors")
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
  check(title_of(c):find("recording", 1, true), "title says recording: " .. title_of(c))
  eq(c.frame.x, (1440 - 380) / 2, "top-center x")
  eq(c.frame.y, 12, "top-center y")
  eq(menubars[1].title, " REC", "menubar mark while recording")
  find_taps()
  check(esc_tap.enabled, "Esc tap armed while a take is active")
  press_right_option()
  check(exists(DATA .. "/dict.stop"), "stop-file written")
  check(title_of(live_canvas()):find("transcribing", 1, true), "title after stop")
  write_status("dict", "rewriting", "hello there world", "preset email")
  advance(0.2)
  c = live_canvas()
  check(title_of(c):find("rewriting", 1, true), "rewriting shown: " .. title_of(c))
  eq(body_of(c), "hello there world", "transcript shown while processing")
  write_status("dict", "done", "Hello there, world.", "pasted into the focused app")
  t:finish(0, "Hello there, world.\n", "")
  c = live_canvas()
  check(title_of(c):find("done", 1, true), "done")
  eq(body_of(c), "Hello there, world.", "final text")
  eq(menubars[1].deleted, true, "menubar removed on exit")
  advance(3)
  eq(live_canvas(), nil, "banner clears after the linger")
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
  check(title_of(live_canvas()):find("cancelling", 1, true), "cancelling shown")
  eq(press_esc(), false, "second Esc passes through")
  press_right_option()
  check(not exists(DATA .. "/dict.stop"), "Right Option ignored while cancelling")
  tasks[1]:finish(3, "", "digivoice dict: cancelled\n")
  local c = live_canvas()
  check(title_of(c):find("cancelled", 1, true), "cancelled shown")
  check(body_of(c):find("discarded", 1, true), "says the take was discarded")
  eq(#notifications, 1, "no cancel toast")
  advance(3)
  eq(live_canvas(), nil, "banner clears")
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
  advance(0.2)
  local c = live_canvas()
  check(title_of(c):find("speaking", 1, true), "speaking shown")
  eq(body_of(c), "selected reply text", "selected text shown")
  eq(press_esc(), false, "Esc does not swallow during speech")
  tasks[1]:finish(0, "selected reply text\n", "")
  advance(3)
  eq(live_canvas(), nil, "cleared")
end

function scenarios.speak_failure_goes_to_the_banner()
  double_tap_left_option()
  tasks[1]:finish(1, "", "digivoice speak: nothing selected: select text first\n")
  local c = live_canvas()
  check(title_of(c):find("error", 1, true), "error title")
  eq(body_of(c), "nothing selected: select text first", "reason shown, prefix stripped")
  eq(#notifications, 1, "no toast")
end

function scenarios.error_and_empty_exit_states()
  press_right_option()
  press_right_option()
  tasks[1]:finish(1, "", "digivoice dict: whisper-cli failed (boom)\n")
  eq(body_of(live_canvas()), "whisper-cli failed (boom)", "error detail")
  advance(5)
  press_right_option()
  press_right_option()
  write_status("dict", "empty", "", "nothing recognized")
  tasks[2]:finish(1, "", "digivoice dict: whisper-cli returned no text; take discarded\n")
  local c = live_canvas()
  check(title_of(c):find("nothing heard", 1, true), "empty shown as nothing heard")
  check(body_of(c):find("nothing pasted", 1, true), "says nothing was pasted")
end

function scenarios.stale_status_is_ignored()
  write_status("dict", "done", "OLD TEXT", "")
  clock = clock + 10
  press_right_option()
  local c = live_canvas()
  check(title_of(c):find("recording", 1, true), "stale done must not show")
  eq(body_of(c), "", "no stale text")
end

function scenarios.position_setting()
  write(DATA .. "/settings.json", '{"banner_position": "bottom-right", "live_banner": true}')
  press_right_option()
  local c = live_canvas()
  eq(c.frame.x, 1440 - 380 - 12, "bottom-right x")
  eq(c.frame.y, 900 - c.frame.h - 12, "bottom-right y")
end

function scenarios.bad_position_falls_back()
  write(DATA .. "/settings.json", '{"banner_position": "nowhere"}')
  press_right_option()
  eq(live_canvas().frame.x, (1440 - 380) / 2, "default top-center")
end

function scenarios.banner_disabled()
  write(DATA .. "/settings.json", '{"live_banner": false}')
  press_right_option()
  eq(live_canvas(), nil, "no canvas when disabled")
  eq(menubars[1].title, " REC", "menubar mic indicator stays")
  eq(press_esc(), true, "Esc still cancels")
  check(exists(DATA .. "/dict.cancel"), "cancel-file written")
  tasks[1]:finish(3, "", "")
  eq(live_canvas(), nil, "still no canvas")
  eq(#notifications, 1, "still no toast")
end

function scenarios.animations_toggle()
  local function alphas(c)
    local out = {}
    for i = 5, 29 do out[#out + 1] = c[i].fillColor.alpha end
    return table.concat(out, ",")
  end
  press_right_option()
  local c = live_canvas()
  local first = alphas(c)
  advance(0.3)
  check(alphas(live_canvas()) ~= first, "dots animate")
  tasks[1]:finish(3, "", "")
  advance(5)
  write(DATA .. "/settings.json", '{"banner_animations": false}')
  press_right_option()
  c = live_canvas()
  first = alphas(c)
  advance(0.3)
  eq(alphas(live_canvas()), first, "dots are a still frame")
end

function scenarios.click_expands_long_text()
  local long = string.rep("alpha beta gamma delta ", 30)
  press_right_option()
  write_status("dict", "rewriting", long, "")
  advance(0.2)
  local c = live_canvas()
  local collapsed_h = c.frame.h
  check(c[3].text:find("click: expand", 1, true), "expand hint")
  check(body_of(c):find("…", 1, true), "collapsed text is clipped")
  c.mouse(c, "mouseUp")
  advance(0.2)
  c = live_canvas()
  eq(c.frame.w, 580, "expanded width")
  check(c.frame.h > collapsed_h, "expanded is taller")
  check(c[3].text:find("click: collapse", 1, true), "collapse hint")
  c.mouse(c, "mouseUp")
  advance(0.2)
  eq(live_canvas().frame.w, 380, "collapsed again")
end

function scenarios.cli_missing_is_reported()
  hs.task.new = function() return nil end
  press_right_option()
  eq(live_canvas(), nil, "no banner without a task")
  eq(#notifications, 1, "no toast")
end

local run = scenarios[scenario]
if not run then
  fail("unknown scenario")
end
run()
print("PASS " .. scenario)
