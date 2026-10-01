# digivoice Hammerspoon sample

Sample macOS hotkey adapter for digivoice. **Not** part of the Python package
import path and **not** a hard dependency — copy or symlink into your Hammerspoon
config.

## Locked binds

| Bind | Action |
| --- | --- |
| **Right Option** only | Toggle dictation: first press starts `digivoice dict --toggle`; second press stops recording (stop-file), then digivoice transcribes and pastes. **Not** hold-to-talk. **Not** Left Option. |
| **Ctrl+Shift+Option** | Speak / read-last: `digivoice speak --clipboard-or-history` (clipboard if non-empty, else last digivoice history text). |

Do not invent other default binds in this sample.

## How stop works

Toggle recording uses a **stop-file** (not only the PR1 length cap):

1. First Right Option → Hammerspoon starts  
   `digivoice dict --toggle --stop-file "$DATA/dict.stop"`  
   digivoice clears the stop-file and records with sox/ffmpeg (open-ended, with a safety cap).
2. Second Right Option → Hammerspoon **writes** the stop-file.
3. digivoice notices the file, sends SIGINT to the recorder process group so the
   wav closes cleanly, then continues whisper → history → paste.

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

5. Reload Hammerspoon config (menu → Reload Config).

Optional: `export DIGIVOICE_BIN=/absolute/path/to/digivoice` if PATH lookup fails
inside Hammerspoon's environment.

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
4. Reload Hammerspoon; press **Right Option** once, speak, press again → paste.
5. Copy text, press **Ctrl+Shift+Option** → Piper playback.

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
# in another terminal, to stop:
touch "$HOME/Library/Application Support/digivoice/dict.stop"

# speak clipboard, else last history
digivoice speak --clipboard-or-history
```
