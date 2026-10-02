# digivoice Hammerspoon sample

Sample macOS hotkey adapter for digivoice. **Not** part of the Python package
import path and **not** a hard dependency — copy or symlink into your Hammerspoon
config.

## Locked binds

| Bind | Action |
| --- | --- |
| **Right Option** only (keycode 61) | Toggle dictation: first press starts `digivoice dict --toggle`; second press stops recording (stop-file), then digivoice transcribes and pastes. **Not** hold-to-talk. |
| **Esc** (plain, no modifiers) | Cancel the active dictation: creates the cancel-file; digivoice stops the recorder / whisper / rewrite, deletes the wav, and pastes nothing and logs nothing. Only live while a take is recording, transcribing, or rewriting; Esc is swallowed only when it cancels, otherwise it reaches the focused app. Not used for speech. |
| **Double-tap Left Option** (keycode 58, ~350ms) | Speak selection: `digivoice speak --selection`. Soft-fails if nothing is selected (the banner shows processing or error, not the selection). **No** clipboard or `kind:dict` history fallback. |

Do not invent other default binds in this sample.

## Status banner

Status is a custom overlay banner, not Hammerspoon notifications. Ship model is background-only: no Dock icon (`hs.dockicon.hide`), no digivoice menubar mark, no launch toast. Hammerspoon's own menu-icon preference is separate (turn it off in HS prefs if you want zero menubar chrome).

The banner is **display only** and **status only** (a click toggles density retract → full; it never steals focus and never starts or stops anything). Esc is the only take control. Hover shows one pin under the banner. Pin keeps it on screen and snaps it to the top; unpin hides it until the next take. Drag moves the banner freely; release near one of the 9 anchors snaps and persists the position (`banner_pos.json`); a later take reuses it. The box is the grid plus one short word, with equal padding, and that word sits on the status-icon row. Chrome follows the system appearance (remock dark ground, ivory light ground); RYG status colors stay. Launch does not draw the banner. It appears for a take, an error, a warning, or a pin. `digivoice banner show` reveals a status preview (not the flag text); Esc on a preview only hides it.

| Phase | Animation (digichat 5x5 square grid) | Text shown |
| --- | --- | --- |
| recording | red equalizer wave | recording |
| transcribing / rewriting / pasting / speaking / loading | teal sweep or twinkle | processing |
| error | red `x` | error |
| nothing heard | amber `!` | warning |
| done / cancelled | check or stop square | none (grid only) |
| pinned, idle | quiet gray grid | none |

No titles, no hints, no transcript, no settings UI on the banner.
Density comes from settings: **retract** (default) auto-dismisses a few seconds
after idle/done, **full** stays until collapsed or removed. Neither density
shows the transcript. The banner reads `status.json` that the CLI writes, so
the word matches what digivoice is doing.

Click the banner to toggle density (retract → full → retract).

There is no digivoice menubar mark — the banner grid alone shows take state. Closing the Terminal leaves Hammerspoon running; **Quit** in the digivoice TUI stops the adapter and quits Hammerspoon.

### Banner settings

Stored in digivoice's `settings.json`, changed with the CLI, and **re-read at the start of every take** (no Reload Config needed):

```bash
digivoice settings set live_banner false          # disable the overlay entirely (default true)
digivoice settings set banner_position top-right  # top-center (default) | top-left | top-right
                                                  # | middle-left | middle-right | bottom-center
                                                  # | bottom-left | bottom-right | center
digivoice settings set banner_density full        # retract (hides after a take, default) | full (stays)
digivoice settings set banner_animations false    # still grid frame (default true)
digivoice settings set banner_pinned true         # keep the banner up (default false)
digivoice settings --json                         # show everything
```

Show the banner without dictating (preview; hidden again with `hide`):

```bash
digivoice banner show --text "sound check"
digivoice banner hide   # or: toggle
```

An unknown `banner_position` falls back to `top-center`; an unknown `banner_density` falls back to `retract`.

## How stop works

Toggle recording uses a **stop-file** (there is no UX time limit; the safety cap
only bounds a stuck recorder):

1. First Right Option → Hammerspoon starts  
   `digivoice dict --toggle --stop-file "$DATA/dict.stop"`  
   digivoice clears the stop-file and records with sox/ffmpeg (open-ended, with a safety cap).
2. Second Right Option → Hammerspoon **writes** the stop-file.
3. digivoice notices the file, sends SIGINT to the recorder process group so the
   wav closes cleanly, then continues whisper → optional rewrite → history → paste
   of what was captured (interrupt-safe; no resume-same-take).

On the sox path, ~10s of silence pauses the take the same way (the recorder ends
itself; the wav is kept and dictation proceeds with what was captured) — long
dictation is never cut mid-speech.

SIGINT/SIGTERM to the digivoice process itself takes the same early-stop path
(Hammerspoon falls back to `task:terminate()` if the stop-file cannot be written).

Default stop-file: `~/Library/Application Support/digivoice/dict.stop`  
(or `$DIGIVOICE_DATA_DIR/dict.stop`).

## Install

1. Install [Hammerspoon](https://www.hammerspoon.org/) and grant **Accessibility**.
2. Install digivoice (`uv sync --all-packages` or `pip install -e ./digivoice`) so
   `digivoice` is on `PATH`, or set `DIGIVOICE_BIN` to the absolute binary.
3. Symlink or copy this folder into your Hammerspoon config:

   ```bash
   mkdir -p ~/.hammerspoon
   ln -s /path/to/digithings/digivoice/hammerspoon ~/.hammerspoon/digivoice
   ```

4. In `~/.hammerspoon/init.lua`:

   ```lua
   require("digivoice")
   ```

5. Reload Hammerspoon config (Hammerspoon → Reload Config), or just run bare `digivoice`. That launch opens Hammerspoon if it is not running, adds `require("digivoice")` to `~/.hammerspoon/init.lua` when the adapter is installed but not required, hides the Dock icon, and shows the banner. No digivoice menubar step. Cap a few seconds; never blocks the shell. Closing that Terminal leaves HS up; TUI **Quit** tears it down.

Optional: `export DIGIVOICE_BIN=/absolute/path/to/digivoice` if PATH lookup fails
inside Hammerspoon's environment.

## Refreshing the Mac after an update (Chris's runbook)

After a digivoice change lands on `develop`:

1. Update the checkout and the CLI it runs:

   ```bash
   cd ~/path/to/digithings
   git pull origin develop
   uv sync --all-packages        # or: pip install -e ./digivoice
   ```

   The CLI is an editable install, so the pull alone updates the Python code; `uv sync` only matters if dependencies changed.

2. Reload the Lua adapter: Hammerspoon menubar icon → **Reload Config** (or run `hs.reload()` in the Hammerspoon console). The adapter is symlinked from the checkout (`~/.hammerspoon/digivoice` → `digithings/digivoice/hammerspoon`), so reloading picks up the new `init.lua` and `banner_core.lua`. Settings changes need no reload.

3. Check which CLI Hammerspoon will run. Lookup order: `$DIGIVOICE_BIN`, `command -v digivoice`, `<checkout>/.venv/bin/digivoice` (derived from the symlink), `~/.local/bin/digivoice`, `~/.venv/bin/digivoice`, then a login-shell `command -v digivoice`. Confirm with `hs -c 'return require("digivoice")'` after reload, or watch `dict`/`speak` argv. If it is wrong or missing, point it at the right binary and reload:

   ```bash
   launchctl setenv DIGIVOICE_BIN "$HOME/path/to/digithings/.venv/bin/digivoice"   # then quit/reopen Hammerspoon
   ```

   (or `export DIGIVOICE_BIN=…` in the shell that launches Hammerspoon).

4. Verify the CLI is new enough: `digivoice cancel --help` and `digivoice status` must exist. A stale CLI behind a new `init.lua` still dictates, but Esc cannot discard the take (the banner will honestly report `done`).

5. Smoke test: **Right Option**, say a few words, press **Esc** → banner says `cancelled`, nothing pasted, `digivoice history --last 1` unchanged. Then **Right Option**, speak, **Right Option** → text appears in the banner, then pastes.


## Mic + Accessibility TCC runbook

macOS will not prompt until the tool first needs the grant. Expect two prompts:

### Microphone

- **Who asks:** `sox` or `ffmpeg` (and sometimes Terminal / Hammerspoon if they
  own the child process) when `digivoice dict` first records.
- **Where to grant:** System Settings → Privacy & Security → Microphone.
- **Enable for:** Hammerspoon, and the terminal you use to run `digivoice doctor`
  / manual `dict` (Terminal, iTerm, Warp, etc.).
- **Symptom if denied:** `digivoice dict` exits 1 with a one-line capture error;
  no hang.

### Accessibility

- **Who asks:** `osascript` sending Command-V for paste (and Cmd+C for
  `speak --selection`).
- **Where to grant:** System Settings → Privacy & Security → Accessibility.
- **Enable for:** Hammerspoon (hotkey-driven dict/speak) and your terminal for
  manual CLI use.
- **Symptom if denied:** dictation still succeeds — transcript on stdout and in
  the clipboard via `pbcopy`; stderr notes that paste needs Accessibility.

### Checklist after a fresh Mac login

1. `digivoice doctor` — whisper-cli, piper, sox/ffmpeg, `ggml-base.en.bin`, Piper voice.
2. Grant Mic to Hammerspoon (+ terminal).
3. Grant Accessibility to Hammerspoon (+ terminal).
4. Reload Hammerspoon; press **Right Option** once, speak, press again → paste. Press **Esc** mid-take → discarded.
5. Select a coding CLI reply, **double-tap Left Option** → Piper playback (nothing selected stays on the grid).

## Piper voice on Chris's Mac

`speak` needs a Piper `.onnx` voice (plus the matching `.onnx.json` beside it):

```bash
# recommended: explicit path
export DIGIVOICE_PIPER_VOICE="$HOME/Library/Application Support/digivoice/models/en_US-lessac-medium.onnx"

# or drop the .onnx (+ .onnx.json) into the models directory and omit the env var
# digivoice picks the first *.onnx there
```

Download voices from the Piper voices release (e.g. `en_US-lessac-medium`). Keep
weights out of git. `digivoice doctor` checks that `piper` is on `PATH` (or
`~/.local/bin/piper`); it does not require the voice file for exit 0 today —
a missing voice fails soft on `speak` with a clear stderr line.

## Manual CLI equivalents

```bash
# toggle dict with stop-file (what Hammerspoon runs)
digivoice dict --toggle --stop-file "$HOME/Library/Application Support/digivoice/dict.stop"
# in another terminal, to stop (transcribe + paste):
touch "$HOME/Library/Application Support/digivoice/dict.stop"
# or to cancel (discard: no paste, no history entry):
digivoice cancel

# speak selection only (what Hammerspoon runs)
digivoice speak --selection
```

### Coding CLI readout (OpenCode / Claude / Cursor)

**Double-tap Left Option** speaks the **current selection** only. After an assistant reply:

1. Select the reply text in the terminal/TUI, then
2. Double-tap **Left Option** (within ~350ms).

If nothing is selected, digivoice exits 1 with a one-line hint and the banner
shows it — it will **not** read the clipboard or last dictation from history.
**Right Option** dict toggle is unchanged. Ctrl+Shift+Option is **not** bound.

