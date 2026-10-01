# Review: digivoice banner, Esc cancel, empty-take discard

**Reviewer:** claude-sonnet-5-thinking-high subagent (fresh-context, in-session review; did not author this diff)
**Subject:** branch `cursor/digivoice-banner-esc-discard-379b`, tip commit `01e6bb1c31c4f519aebefd266765a48d43aa8afe`
(3 commits: `85656c393`, `610a44841`, `01e6bb1c3`; diff = `git diff origin/develop...HEAD`)

**Verdict: APPROVE WITH FIXES**

## Severity counts

| Severity | Count |
| --- | --- |
| blocker | 0 |
| major | 1 |
| minor | 2 |
| nit | 2 |

## Commands run

```
cd /workspace && /tmp/dvvenv/bin/python -m pytest tests/dvo -m unit -q -p no:cacheprovider
# -> 168 passed in 3.14s (includes 19 lua-backed tests under test_hammerspoon_lua.py; lua5.4 is on PATH)

/tmp/dvvenv/bin/ruff check digivoice/src tests/dvo && /tmp/dvvenv/bin/ruff format --check digivoice/src tests/dvo
# -> All checks passed! / 33 files already formatted
```

Both pre-flight gates from `digivoice/AGENTS.md` are green. No source file was modified during this review; all mutation/repro work ran against throwaway copies under `/tmp`.

## Findings

### 1. [Major] Narrow TOCTOU race lets a late Esc land after the "last" cancel check but still get pasted and logged — contradicts the documented commit point

**Evidence:**
- `digivoice/src/digivoice/cli.py:339-341` — the last `cancel.requested()` re-check, immediately followed by the empty-text check.
- `digivoice/src/digivoice/cli.py:350-354` — `reporter.update("pasting", ...)`, a `status.json` write (mkdir + write + `os.replace`), happens **after** that last check.
- `digivoice/src/digivoice/cli.py:355-361` — `history_file`/`history_log.append_entry(...)` run after the status write, with **no further cancel check** in between.
- `digivoice/ARCHITECTURE.md:124` explicitly claims: *"The last check is immediately before the history append; once the history line is written the take is committed and a late cancel is ignored."* That is not what the code does — the real last check is before a status-file write and an empty-text check, not immediately before the append.

**Verification:** confirmed with a live repro (not merely code reading). I monkey-patched `StatusReporter.update` so that the *first* call with `state="pasting"` writes the cancel-file at that exact moment (simulating Esc landing in this specific gap), then ran `dict --hold` through the real `run()`/`_dict()` code path with a `FakeRunner`:

```
exit code: 0
stdout: 'ship it.\n'
history exists: True
history contents: {"ts":"...","kind":"dict","text":"ship it.","wav":".../recordings/dict-....wav"}
wav files left: ['.../recordings/dict-....wav']
states seen: ['recording', 'transcribing', 'pasting', 'done']
```

The take completed, pasted, and was logged to history even though the cancel-file existed before the history append ran — i.e. a real violation of product lock #3 ("Esc cancels... discard completely, no paste, no history entry, no leftover wav") and of the ARCHITECTURE.md claim, under a demonstrated (if narrow) timing window.

**Why this is a real, if low-probability, window:** the gap between the check at line 339 and the append at line 357 contains a `Path.mkdir` + file write + `os.replace` (status.json). On a slow or network-backed data dir this window widens; on local SSD it's sub-millisecond. A human physically pressing Esc is extremely unlikely to land in it, but this is exactly the "ordering vs. history append" race class the review was asked to check, and it is reproducible on demand (as shown above), not merely theoretical.

**Suggested fix:** move the final `cancel.requested()` check to be the last statement before `history_log.append_entry(...)` (i.e., re-check again after the `reporter.update("pasting", ...)` call and the `text_out.strip()` guard), or restructure so no I/O happens between the check and the append. Then update `ARCHITECTURE.md:124` only if the recheck's exact position changes materially.

### 2. [Minor] Hammerspoon's `kill9()` fallback can orphan the recorder and leave a wav behind if the cancel-file write itself fails

**Evidence:** `digivoice/hammerspoon/init.lua:396-401`:
```lua
if not write_file(CANCEL_FILE, "cancel\n") then
    pcall(function()
      s.task:kill9()
    end)
end
```
`s.task:kill9()` sends `SIGKILL` only to the `digivoice` CLI process that Hammerspoon launched via `hs.task`. The actual recorder (`sox`/`ffmpeg`) is spawned by that CLI with `start_new_session=True` (`digivoice/src/digivoice/capture.py:218-221`), i.e. in its own session, decoupled from the CLI's process group.

**Verification:** reproduced the underlying OS behavior directly (SIGKILL does not propagate to a `start_new_session=True` child):
```
parent pid: 43400 child pid: 43401
child still alive after parent SIGKILL: True
```
So if the Lua side's cancel-file write fails (disk full, permissions, unwritable `DIGIVOICE_DATA_DIR`) and falls back to `kill9()`, the orphaned recorder process keeps running and keeps writing to the wav file until its own internal safety cap (up to 60s in toggle mode) — i.e. a leftover wav and no cancellation of the actual recording, violating "no leftover wav" in this one fallback path. This is a secondary failure mode (requires the cancel-file write to fail first), so it is minor rather than major, but it is a real gap, not merely theoretical.

**Suggested fix:** when the cancel-file write fails, also attempt to signal the recorder's process group (not reachable directly from Lua) — practically, either retry the cancel-file write against a different path/tmp dir, or have `digivoice`'s own signal handling be the single source of truth and have `kill9()` only ever be used as a last resort *after* a short grace period, logging the leftover-wav risk to the Hammerspoon console so it's visible instead of silent.

### 3. [Minor] Test harness doesn't model real `hs.canvas` hit-testing — `trackMouseUp` regressions would ship silently

**Evidence:** `tests/dvo/lua/hs_flows.lua:104-110` (`methods.mouseCallback`) and the `c.mouse(c, "mouseUp")` helper used by `scenarios.click_expands_long_text` (`hs_flows.lua:484, 488`) invoke the registered callback unconditionally, with no `id`/`x`/`y` and no check of which element (if any) has mouse tracking enabled. Real Hammerspoon only invokes `canvas:mouseCallback` when the click lands on an element with `trackMouseUp`/`trackMouseDown`/etc. set (`digivoice/hammerspoon/init.lua:201-204` sets `trackMouseUp = true` only on the background rectangle).

**Verification:** mutation test against an isolated copy of the adapter (not the real source tree) — removed `trackMouseUp = true` from `init.lua`'s background element and re-ran every scenario in `hs_flows.lua`:
```
[mutD-remove-trackMouseUp] total failures: 0
```
All 16 scenarios still pass with that attribute removed, confirming the harness cannot detect a regression that would silently break "click to expand" in real Hammerspoon (clicking the banner would stop doing anything). By contrast, the harness *does* correctly catch other regressions I injected (making `pasting` wrongly cancellable, adding an extra `hs.notify` call on cancel, removing `clickActivating(false)`) — see below — so this is a specific, narrow blind spot rather than a wholesale harness failure.

```
[mutA-pasting-cancellable]  FAIL esc_passes_through_once_pasting (caught)
[mutB-clean-no-clickActivating] FAIL dict_banner_recording_then_done (caught)
[mutC-clean-extra-notify-on-cancel] FAIL esc_cancels_and_swallows, banner_disabled (caught)
```

**Suggested fix:** not a blocker for this PR (it's a pre-existing fidelity gap in the shared fake, and `trackMouseUp` is correctly set in the current code), but worth a follow-up: have the fake's `mouse()` helper take a point and only fire the callback for elements whose frame contains that point and which have `trackMouseUp`/`trackMouseDown` set, so a future accidental removal of that attribute is caught.

### 4. [Nit] `_NON_SPEECH_MARKER` accepts mismatched bracket/paren delimiters

**Evidence:** `digivoice/src/digivoice/transcribe.py:26-29`:
```python
_NON_SPEECH_MARKER = re.compile(
    r"[\[(]\s*(?:blank[_ ]audio|silence|no speech|inaudible)\s*[\])]", re.IGNORECASE
)
```
`[\[(]` (opener: `[` or `(`) and `[\])]` (closer: `]` or `)`) are independent character classes, so e.g. `"[blank_audio)"` or `"(silence]"` would also match and be stripped, even though whisper.cpp never actually emits mismatched delimiters. Cosmetic only — confirmed by reading the regex; not independently exploitable given whisper.cpp's fixed output format, and the existing parametrized tests (`tests/dvo/test_transcribe.py`) all use correctly-paired markers so this doesn't affect current behavior.

**Suggested fix (optional):** split into two alternatives (`\[...\]` and `\(...\)`) if stricter matching is ever wanted; not worth doing unless touching this file for another reason.

### 5. [Nit] Small duplication between `capture.py` and `cli.py`

**Evidence:** `digivoice/src/digivoice/capture.py:130-134` (`_discard`) and `digivoice/src/digivoice/cli.py:233-238` (`_discard_wav`) are near-identical "unlink missing_ok, swallow OSError" helpers in two modules. Not a bug — both correctly swallow `OSError` and both are soft-fail — just a minor duplication that a shared helper (e.g. in `status.py` or a small `fsutil` module) could remove if touched again.

## What I checked and found correct (no finding, noted for completeness)

- **`run_command_cancellable`'s `communicate()` retry loop** (`runner.py:117-124`): verified against CPython's actual `subprocess.Popen.communicate`/`_communicate`/`_save_input` source — retrying with `input=None` after a `TimeoutExpired` is the officially supported pattern (`_save_input` only captures `input` once; `_communication_started` guards against resending), so the comment "communicate() keeps the input it already queued; do not send it twice" is accurate and the pattern is correct, not a bug.
- **Process-group kill** (`runner.py:72-83`, `capture.py:144-179`): `start_new_session=True` + `os.killpg(proc.pid, ...)` is correct because `setsid()` makes the child both session and process-group leader, so `proc.pid == pgid`. Confirmed the "orphaned child survives direct-pid SIGKILL" assumption behind finding #2 with a live repro.
- **Soft-fail on status writes**: `StatusReporter.update` catches `OSError` only around the write/replace, never changes the caller's control flow/exit code; `test_unwritable_status_never_fails_the_take` exercises this (status.json path replaced by a directory) and passes.
- **Blank-paste guards**: `paste()`/`copy_to_clipboard()` (`paste.py`) both refuse blank text before doing anything, verified by `test_blank_text_is_never_pasted_or_copied` (parametrized over `""`, `"   "`, `"\n"`), and `runner.calls == []` confirms no subprocess is even spawned for a blank take.
- **Cancellable-state table parity**: Python's `StatusState` literal (`status.py`) and Lua's `M.STATE_MATRIX`/`M.LABELS`/`RANK` (`banner_core.lua`) cover the same set of states with no gaps.
- **Scope**: `digivoice/src/digivoice/speak.py` (`read_selection`) is untouched by this diff (confirmed via `git diff ... -- digivoice/src/digivoice/speak.py` = empty); no live-streaming STT was added (explicitly documented as deferred in both `ARCHITECTURE.md` and `hammerspoon/README.md`); the only `hs.notify` call left in `init.lua` is the launch toast (`grep -n "hs\.notify" digivoice/hammerspoon/*.lua` returns exactly one hit).
- **"Chris's runbook" section** in `hammerspoon/README.md` is not scope creep — "Chris's Mac" is a pre-existing naming convention in this doc from an earlier commit (`5bf373d44`, prior to this branch).
- Lua↔doc consistency: the state→glyph/animation table in `hammerspoon/README.md` matches `banner_core.lua`'s `MATRIX`/`body_for` exactly (checked each state's color/glyph/text claim against the source).


## Resolution (author, after review)

| # | Severity | Status | Where |
| --- | --- | --- | --- |
| 1 | major | fixed: the cancel re-check now sits immediately before `history_log.append_entry`; regression test `test_cancel_arriving_just_before_the_history_append_still_discards` fails without it (mutation-checked) | `digivoice/src/digivoice/cli.py` |
| 2 | minor | fixed: no `kill9()` fallback; if the cancel-file cannot be written the take continues, Esc is not swallowed, and the console says so; scenario `unwritable_cancel_file_never_kills_the_cli` | `digivoice/hammerspoon/init.lua`, `tests/dvo/lua/hs_flows.lua` |
| 3 | minor | partly fixed: harness now asserts the background element has `trackMouseUp = true` and a mouse callback is registered. Real hit-testing is not modelled; verify click-to-expand on the Mac | `tests/dvo/lua/hs_flows.lua` |
| 4 | nit | fixed: marker regex requires matching `[ ]` / `( )` pairs | `digivoice/src/digivoice/transcribe.py` |
| 5 | nit | fixed: single `discard_wav` helper in `capture.py`, imported by `cli.py` | `digivoice/src/digivoice/capture.py` |

Re-run after fixes: `pytest tests/dvo -m unit` 170 passed; `ruff check` / `ruff format --check` clean.
