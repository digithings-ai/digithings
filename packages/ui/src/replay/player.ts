/**
 * Playback for a replay file. The transcript is fully rendered in the HTML;
 * this script only reveals it. No network, no model.
 *
 * Turns stay in document order: the question, then each block (a work chain
 * or a markdown answer). Arrow keys move a whole turn. Space plays.
 */
export function replayPlayerScript(): string {
  return `
(function () {
  var root = document.getElementById("replay");
  if (!root) return;
  var turns = Array.prototype.slice.call(root.querySelectorAll("[data-replay-turn]"));
  var playBtn = document.getElementById("replay-play");
  var fullBtn = document.getElementById("replay-full");
  var speedEl = document.getElementById("replay-speed");
  var themeEl = document.getElementById("replay-theme");
  var viewEl = document.getElementById("replay-view");
  var scroller = document.getElementById("replay-scroll");
  var revealed = turns.length;
  var playing = false;
  var timer = 0;
  var partial = null;

  function speed() {
    var value = speedEl ? Number(speedEl.value) : 1;
    return value > 0 ? value : 1;
  }
  function fullText(node) {
    return node ? node.getAttribute("data-full") || "" : "";
  }
  function setTyped(node, value, caret) {
    if (!node) return;
    node.textContent = value;
    if (!caret) return;
    var bar = document.createElement("span");
    bar.className = "replay-caret";
    bar.setAttribute("aria-hidden", "true");
    node.appendChild(bar);
  }
  function blocksOf(turn) {
    return Array.prototype.slice.call(turn.querySelectorAll("[data-replay-block]"));
  }
  function stepsOf(block) {
    return Array.prototype.slice.call(block.querySelectorAll("[data-replay-step]"));
  }
  function restoreAnswer(block) {
    var live = block.querySelector("[data-replay-live]");
    var finalHtml = block.querySelector("template");
    if (live && finalHtml) live.innerHTML = finalHtml.innerHTML;
  }
  function showBlockFull(block) {
    block.hidden = false;
    if (block.getAttribute("data-replay-block") === "text") {
      restoreAnswer(block);
      return;
    }
    stepsOf(block).forEach(function (step) {
      step.hidden = false;
      var result = step.querySelector("[data-replay-result]");
      if (result) result.hidden = false;
      var body = step.querySelector("[data-replay-reasoning]");
      if (body) setTyped(body, fullText(body), false);
    });
  }
  function showTurnFull(turn) {
    turn.hidden = false;
    var user = turn.querySelector("[data-replay-user]");
    setTyped(user, fullText(user), false);
    blocksOf(turn).forEach(showBlockFull);
  }
  function viewOpens() {
    return !!(viewEl && viewEl.value === "verbose");
  }
  function applyView() {
    var open = viewOpens();
    root.querySelectorAll("details[data-replay-disclosure]").forEach(function (el) {
      el.open = open;
      var summary = el.querySelector("summary");
      if (summary) summary.setAttribute("aria-expanded", open ? "true" : "false");
    });
    if (viewEl) root.setAttribute("data-view", viewEl.value);
  }
  function paintPartial(turn) {
    turn.hidden = false;
    var user = turn.querySelector("[data-replay-user]");
    var userFull = fullText(user);
    var blocks = blocksOf(turn);
    if (partial.phase === "user") {
      setTyped(user, userFull.slice(0, partial.chars), partial.chars < userFull.length);
      blocks.forEach(function (block) { block.hidden = true; });
      return;
    }
    setTyped(user, userFull, false);
    blocks.forEach(function (block, index) {
      if (index > partial.block) {
        block.hidden = true;
        return;
      }
      block.hidden = false;
      if (index < partial.block) {
        showBlockFull(block);
        return;
      }
      paintBlock(block);
    });
  }
  function paintBlock(block) {
    if (block.getAttribute("data-replay-block") === "text") {
      var live = block.querySelector("[data-replay-live]");
      var plain = block.getAttribute("data-plain") || "";
      if (partial.chars >= plain.length) restoreAnswer(block);
      else setTyped(live, plain.slice(0, partial.chars), true);
      return;
    }
    var details = block.querySelector("details");
    if (details) details.open = true;
    var steps = stepsOf(block);
    steps.forEach(function (step, index) {
      step.hidden = index > partial.step;
      if (index > partial.step) return;
      var result = step.querySelector("[data-replay-result]");
      if (result) result.hidden = index === partial.step && partial.chars < 2;
      if (index !== partial.step) return;
      var body = step.querySelector("[data-replay-reasoning]");
      if (!body) return;
      var full = fullText(body);
      setTyped(body, full.slice(0, partial.chars), partial.chars < full.length);
    });
  }
  function paint() {
    turns.forEach(function (turn, index) {
      if (partial && index === partial.turn) paintPartial(turn);
      else if (index < revealed) showTurnFull(turn);
      else turn.hidden = true;
    });
    root.setAttribute("data-revealed", String(revealed));
    root.setAttribute("data-mode", playing ? "playing" : revealed >= turns.length ? "full" : "paused");
    if (playBtn) playBtn.textContent = playing ? "Pause" : "Play";
  }
  function beginPartial() {
    if (revealed >= turns.length) {
      partial = null;
      playing = false;
      return;
    }
    partial = { turn: revealed, phase: "user", block: 0, step: 0, chars: 0 };
  }
  function finishTurn() {
    revealed = partial.turn + 1;
    partial = null;
    if (revealed >= turns.length) playing = false;
    else if (playing) beginPartial();
  }
  function advance() {
    if (!partial) return;
    var turn = turns[partial.turn];
    if (!turn) { partial = null; playing = false; return; }
    var rate = Math.max(1, Math.round((partial.phase === "user" ? 2 : 4) * speed()));
    if (partial.phase === "user") {
      var userLen = fullText(turn.querySelector("[data-replay-user]")).length;
      if (partial.chars < userLen) partial.chars += rate;
      else enterBlocks();
      return;
    }
    var blocks = blocksOf(turn);
    var block = blocks[partial.block];
    if (!block) { finishTurn(); return; }
    if (block.getAttribute("data-replay-block") === "text") {
      var plain = block.getAttribute("data-plain") || "";
      if (partial.chars < plain.length) partial.chars += rate;
      else nextBlock(blocks);
      return;
    }
    var steps = stepsOf(block);
    var step = steps[partial.step];
    if (!step) { nextBlock(blocks); return; }
    var kind = step.getAttribute("data-replay-step");
    if (kind === "reasoning") {
      var len = fullText(step.querySelector("[data-replay-reasoning]")).length;
      if (partial.chars < len) partial.chars += rate;
      else nextStep(steps, blocks);
    } else if (kind === "tool") {
      if (partial.chars < 2) partial.chars += 1;
      else nextStep(steps, blocks);
    } else if (partial.chars < 1) {
      partial.chars += 1;
    } else {
      nextStep(steps, blocks);
    }
  }
  function enterBlocks() {
    var blocks = blocksOf(turns[partial.turn]);
    partial.phase = "block";
    partial.block = 0;
    partial.step = 0;
    partial.chars = 0;
    if (blocks.length === 0) finishTurn();
  }
  function nextStep(steps, blocks) {
    partial.step += 1;
    partial.chars = 0;
    if (partial.step >= steps.length) nextBlock(blocks);
  }
  function nextBlock(blocks) {
    partial.block += 1;
    partial.step = 0;
    partial.chars = 0;
    if (partial.block >= blocks.length) finishTurn();
  }
  function schedule() {
    window.clearTimeout(timer);
    if (!playing) return;
    if (!partial) beginPartial();
    var wait = partial && partial.phase === "block" && partial.chars === 0 ? 260 : 32;
    timer = window.setTimeout(function () {
      advance();
      paint();
      if (scroller) scroller.scrollTop = scroller.scrollHeight;
      schedule();
    }, Math.max(16, Math.round(wait / speed())));
  }
  function nextTurn() {
    playing = false;
    window.clearTimeout(timer);
    if (partial) finishTurn();
    else if (revealed < turns.length) revealed += 1;
    paint();
  }
  function prevTurn() {
    playing = false;
    window.clearTimeout(timer);
    if (partial) partial = null;
    else if (revealed > 0) revealed -= 1;
    paint();
  }
  function showTranscript() {
    playing = false;
    window.clearTimeout(timer);
    partial = null;
    revealed = turns.length;
    paint();
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
  }
  if (playBtn) playBtn.addEventListener("click", function () {
    if (!playing && revealed >= turns.length && !partial) {
      revealed = 0;
      beginPartial();
    }
    playing = !playing;
    if (!playing) window.clearTimeout(timer);
    paint();
    schedule();
  });
  if (fullBtn) fullBtn.addEventListener("click", showTranscript);
  if (speedEl) speedEl.addEventListener("change", function () {
    root.setAttribute("data-speed", speedEl.value);
  });
  if (themeEl) themeEl.addEventListener("change", function () {
    var parts = themeEl.value.split("|");
    var palette = parts[0] || "default";
    var mode = parts[1] === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", mode);
    if (palette === "default") document.documentElement.removeAttribute("data-palette");
    else document.documentElement.setAttribute("data-palette", palette);
    document.documentElement.classList.toggle("light", mode === "light");
    document.documentElement.classList.toggle("dark", mode !== "light");
  });
  if (viewEl) viewEl.addEventListener("change", applyView);
  root.querySelectorAll("details[data-replay-disclosure]").forEach(function (el) {
    el.addEventListener("toggle", function () {
      var summary = el.querySelector("summary");
      if (summary) summary.setAttribute("aria-expanded", el.open ? "true" : "false");
    });
  });
  window.addEventListener("keydown", function (event) {
    var target = event.target;
    var tag = target && target.tagName;
    if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
    // Space and arrows on a focused control (a summary, button or link) keep
    // their native meaning: Space opens a tool card, it does not start playback.
    if (target && target.closest && target.closest("summary, button, a, [contenteditable]")) return;
    if (event.key === "ArrowRight") { event.preventDefault(); nextTurn(); }
    else if (event.key === "ArrowLeft") { event.preventDefault(); prevTurn(); }
    else if (event.key === " ") { event.preventDefault(); if (playBtn) playBtn.click(); }
  });
  applyView();
  paint();
  if (scroller && revealed >= turns.length) scroller.scrollTop = scroller.scrollHeight;
})();
`;
}
