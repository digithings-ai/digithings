# digivoice Hammerspoon sample

Sample macOS hotkey adapter for digivoice. **Not** part of the Python package
import path and **not** a hard dependency — copy or symlink into your Hammerspoon
config.

## Locked binds

| Bind | Action |
| --- | --- |
| **Right Option** only (keycode 61) | Toggle dictation: first press starts `digivoice dict --toggle`; second press stops recording (stop-file), then digivoice transcribes and pastes. **Not** hold-to-talk. |
| **Esc** (plain, no modifiers) | Cancel the active dictation: creates the cancel-file; digivoice stops the recorder / whisper / rewrite, deletes the wav, and pastes nothing and logs nothing. Only live while a take is recording, transcribing, or rewriting; Esc is swallowed only when it cancels, otherwise it reaches the focused app. Not used for speech. |
| **Double-tap Left Option** (keycode 58, ~350ms) | Speak selection: `digivoice speak --selection`. Soft-fails if nothing is selected (the grid is the status; full density shows the selection). **No** clipboard or `kind:dict` history fallback. |

Do not invent other default binds in this sample.

## Status banner

Status is a custom overlay banner, not Hammerspoon notifications. Ship model is background-only: no Dock icon (`hs.dockicon.hide`), no digivoice menubar mark, no launch toast. Hammerspoon's own menu-icon preference is separate (turn it off in HS prefs if you want zero menubar chrome).

The banner is **display only** (a click toggles density retract → full; it never steals focus and never starts or stops anything). Esc is the only take control. Hover shows icon-only copy + close below the banner (stacked when retracted, right-aligned row when full), using the digichat copy and close marks; close hides instantly and never discards. Drag moves the banner freely; release near one of the 9 anchors snaps and persists the position (`banner_pos.json`); a later take reuses it. Center pins keep the center on expand, edge pins grow outward. Dictated text appears at once. The box hugs the text with equal padding, and the first line sits on the status-icon row. Full caps near half the screen height and wheel-scrolls with no scrollbar. Chrome follows the system appearance (remock dark ground, ivory light ground); RYG status colors stay. Status is the grid only — no discarded/empty/error sentence beside it. The banner is hidden by default: `digivoice banner show [--text T]` (or `hide` / `toggle`) spawns a preview with no dictation; Esc on a preview only hides it.

| Phase | Animation (digichat 5x5 square grid) | Text shown |
| --- | --- | --- |
| recording | red equalizer wave | none (grid only) |
| transcribing | teal diagonal sweep | none yet (no live streaming STT) |
| rewriting | teal circular sweep | the transcript, in full density |
| pasting | teal downward sweep | the text being pasted |
| speaking | teal equalizer | the selected text |
| loading | teal grid twinkle | none |
| done / cancelled / nothing heard / error | check / stop square / `!` / `x` glyph | final transcript, or nothing (the grid is the status) |

No titles, no hints, no settings UI on the banner — state reads from the grid alone.
Density comes from settings: **retract** (default) is the grid only and
auto-dismisses a few seconds after idle/done, **full** shows the whole
transcript and stays until collapsed or removed. The banner reads `status.json`
that the CLI writes, so it shows exactly what digivoice is doing.

Click the banner to toggle density (retract → full → retract).

There is no digivoice menubar mark — the banner grid alone shows take state. Closing the Terminal leaves Hammerspoon running; **Quit** in the digivoice TUI stops the adapter and quits Hammerspoon.

### Banner settings

Stored in digivoice's `settings.json`, changed with the CLI, and **re-read at the start of every take** (no Reload Config needed):

```bash
digivoice settings set live_banner false          # disable the overlay entirely (default true)
digivoice settings set banner_position top-right  # top-center (default) | top-left | top-right
                                                  # | middle-left | middle-right | bottom-center
                                                  # | bottom-left | bottom-right | center
digivoice settings set banner_density full        # retract (grid only, default) | full (stays)
digivoice settings set banner_animations false    # still grid frame + instant text (default true)
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

One-command from a checkout (CLI + Hammerspoon symlink + models bootstrap):

```bash
bash digivoice/scripts/install.sh
```

That script records `git rev-parse HEAD` as `DIGIVOICE_TIP_SHA`, installs the CLI with `uv tool install -e ./digivoice` when uv is on PATH (no pre-activated venv), and **never rsyncs** this folder over `~/Library/Application Support/digivoice/hammerspoon`. Live adapter path is a symlink:

```bash
mkdir -p ~/.hammerspoon
ln -s /path/to/digithings/digivoice/hammerspoon ~/.hammerspoon/digivoice
```

(`digivoice install` does that symlink for you.) Then `require("digivoice")` in `~/.hammerspoon/init.lua` (also added by install / bare `digivoice`).

Manual path if you skip the script:

1. Install [Hammerspoon](https://www.hammerspoon.org/) and grant **Accessibility**.
2. Install digivoice (`uv tool install -e ./digivoice`, or `uv sync --all-packages` /
   `pip install -e ./digivoice` in a venv) so `digivoice` is on `PATH`, or set
   `DIGIVOICE_BIN` to the absolute binary.
3. Symlink this folder (do **not** copy into Application Support):

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

## Mac reinstall runbook (SHA-safe)

Never rsync `digivoice/hammerspoon/` over `~/Library/Application Support/digivoice/hammerspoon` without a tip SHA check. An unguarded TUI-branch sync wiped the #4965 banner tip.

1. Confirm the checkout tip before touching the adapter:

   ```bash
   git -C ~/path/to/digithings rev-parse HEAD
   # compare with {data_dir}/install.json  and, if present,
   # ~/Library/Application\ Support/digivoice/hammerspoon/.digivoice-tip
   ```

   If the Application Support copy exists and the stamp does not match, **leave it alone**. Refresh via the `~/.hammerspoon/digivoice` symlink only.

2. Reinstall from the checkout (one command):

   ```bash
   bash digivoice/scripts/install.sh
   ```

   Or, if the CLI is already on PATH: `digivoice update` (add `--fetch-models` when `ggml-base.en.bin` is missing).

3. Smoke checklist (in order):

   1. `digivoice doctor` — whisper-cli, piper, sox/ffmpeg, `ggml-base.en.bin`, adapter present.
   2. `digivoice reload` — bounded `hs` reload; adapter realpath should be this checkout.
   3. `digivoice banner show` — preview banner, no dictation. Confirms background-only HS (no Dock icon, no digivoice menubar, no toast).
   4. **Quit teardown** — TUI **Quit** stops the adapter and quits Hammerspoon. Closing Terminal alone must leave HS running.
   5. **Uninstall → reinstall** — `digivoice uninstall` (data kept) then `bash digivoice/scripts/install.sh` (or `digivoice install`). Doctor + banner show still work. `--purge-data` only when you intend to wipe history/models.

4. Check which CLI Hammerspoon will run. Lookup order: `$DIGIVOICE_BIN`, `command -v digivoice`, `<checkout>/.venv/bin/digivoice` (derived from the symlink), `~/.local/bin/digivoice`, `~/.venv/bin/digivoice`, then a login-shell `command -v digivoice`. If it is wrong or missing, point it at the right binary and reload:

   ```bash
   launchctl setenv DIGIVOICE_BIN "$HOME/path/to/digithings/.venv/bin/digivoice"   # then quit/reopen Hammerspoon
   ```

   (or `export DIGIVOICE_BIN=…` in the shell that launches Hammerspoon).

5. Verify the CLI is new enough: `digivoice cancel --help` and `digivoice status` must exist. A stale CLI behind a new `init.lua` still dictates, but Esc cannot discard the take (the banner will honestly report `done`).

6. Hotkey smoke: **Right Option**, say a few words, press **Esc** → banner says `cancelled`, nothing pasted, `digivoice history --last 1` unchanged. Then **Right Option**, speak, **Right Option** → text appears in the banner, then pastes.


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

