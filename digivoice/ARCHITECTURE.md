# digivoice architecture

Local CLI package at `digivoice/`. No network service and no port. Python 3.12. Console script `digivoice` and `python -m digivoice`.

## Layout

| Path | Role |
| --- | --- |
| `src/digivoice/cli.py` | Argv dispatch and process entry. |
| `src/digivoice/doctor.py` | Host checks and the text report. |
| `src/digivoice/paths.py` | Data, models, recordings, and history locations. Default model id. |
| `src/digivoice/probe.py` | `PATH` lookup and file checks. No shell. |
| `src/digivoice/runner.py` | `CommandRunner` protocol, the real `subprocess.run` runner, stderr tails. |
| `src/digivoice/capture.py` | Microphone to wav. `sox` first, then `ffmpeg`. Toggle early-stop via stop-file / signals. |
| `src/digivoice/transcribe.py` | `whisper-cli` over a wav, transcript cleanup. |
| `src/digivoice/speak.py` | Piper synthesis + local player (`afplay` / `aplay` / `ffplay`). |
| `src/digivoice/history.py` | JSONL append, tolerant read, `--last` / `--grep` / `--copy-last` / `--json`. |
| `src/digivoice/settings.py` | `settings.json` under the data dir; agent-scriptable get/set. |
| `src/digivoice/menu_tree.py` | TTY `/settings` path. Enter opens a folder or a list. A chooser opens on the saved row. A model list shows size and the recommended row. A file in the models directory, or the same filename under LM Studio, Ollama, or MLX, is marked downloaded. The numbered menu still asks before it fetches a missing speech or rewrite file. Each row is a bold name, a bracketed value, and a gray explanation. |
| `src/digivoice/setup.py` | TTY opens the `/settings` path. Pipes keep the numbered wizard. `--print` overview and `recommend_models()` hardware stub (#4939 hook). |
| `src/digivoice/tui.py` | Shared menu blocks and the non-TTY numbered prompts. |
| `src/digivoice/opentui.py` | Replaces a TTY process with the OpenTUI app. |
| `src/digivoice/tui_bridge.py` | Local JSON screen model the OpenTUI process calls. No network. |
| `tui/` | OpenTUI (`@opentui/core`) app: `createCliRenderer`, boxes, and text. |
| `src/digivoice/pixel_hero.py` | 7×10 DIGIVOICE glyph map. The home header paints those glyphs as five half-block rows in `tui.py`. |
| `src/digivoice/catalog.py` | Suggested local STT ggml, Piper voice, and rewrite GGUF list. A download writes a `.partial` sibling and replaces the real file only after every piece is on disk. |
| `src/digivoice/install.py` | `digivoice install` and `digivoice update`: bun, OpenTUI, whisper-cli, Piper, sox, macOS espeak-ng when `libespeak-ng.1.dylib` is missing, arm64 `libpiper_phonemize.1.dylib` beside the real Piper binary, the Hammerspoon adapter at `~/.hammerspoon/digivoice`, and local models. A terminal wizard offers auto (the defaults) or a pick of speech, voice, and rewrite files. A pick does not delete models already on disk. Fetch and runner are injected. No cloud STT/TTS. |
| `src/digivoice/installed_models.py` | Local GGUF and whisper files already installed by LM Studio, Ollama, and MLX Studio. |
| `src/digivoice/home.py` | Bare-`digivoice` home: OpenTUI on a TTY, printed overview otherwise. |
| `src/digivoice/panels.py` | TTY doctor (green ok, red not ok, ready line at the bottom), history browser, and the system pane (reload, reset, restart, update, logs). |
| `src/digivoice/reload.py` | `reload`: CLI path, settings, Lua adapter tip, bounded Hammerspoon reload; clears stale status on failure. |
| `src/digivoice/rewrite.py` | Optional local post-STT rewrite (ollama / llama.cpp). llama-cli runs one turn and the banner is stripped. Fail soft. |
| `src/digivoice/paste.py` | Clipboard plus Command-V into the focused app. Fails soft. Never pastes blank text. |
| `src/digivoice/status.py` | `status.json` feed for the banner, cancel-file token, `CANCELLED_EXIT`. Fails soft. |
| `src/digivoice/errors.py` | `VoiceError` and the capture / transcribe / speak subclasses. |
| `src/digivoice/models.py` | Pydantic v2 models including `RewriteResult` and path/doctor/history types. |
| `hammerspoon/` | Sample hotkey adapter (`init.lua`), status banner logic (`banner_core.lua`, pure Lua), background-only (no Dock/menubar/toast), TCC runbook. |

Every external binary — `sox`, `ffmpeg`, `whisper-cli`, `piper`, `afplay`/`aplay`/`ffplay`, `pbcopy`, `osascript` — is reached
through a `CommandRunner` (argv list, never `shell=True`), except toggle early-stop capture which uses
`subprocess.Popen` so a stop-file or signal can finalize the wav. `Runtime.runner` is the injection
point: `None` / `run_command` means the real runner; tests pass a fake so no test needs a microphone,
sound card, model, or clipboard.

## Terminal UI

A TTY does not draw the Python alternate screen. `opentui.py` replaces the process with `bun digivoice/tui/src/main.js` (the OpenTUI quickstart runtime; `DIGIVOICE_NODE` can point at another binary). That file follows the quickstart: `createCliRenderer` from `@opentui/core`, then `BoxRenderable` and `TextRenderable`. The half-block DIGIVOICE wordmark (block V, letter gap 2 then 1 then 0, rest cube gray 102 and brighter cube 231, or the matching `38;2` RGB only when `COLORTERM` is `truecolor` or `24bit`, never mixed with a cube index) splits each glyph cell into square pixels. A terminal cell is about twice as tall as it is wide, so each pixel is one half of a cell (`▀` / `▄`), sharp, with no rounded corner. The grid is 3×3 when that width fits and the status row plus a few menu rows still fit under it. Otherwise it is 2×2, and 1×1 only when 2×2 does not fit. The face is 15, 10, or 5 rows, in a slot one row taller for the shadow. On a tall window that slot rests about one third of the way down, between one quarter and one third from the top. The menu does not move it. A short window shifts the slot up, and a small window can put it at the top. The slot stays fixed while the page scrolls. Every letter pixel rests in a subdued gray. A level rises and falls inside each column, out of step with the others, and a pixel turns bright only while that level reaches it from the bottom of the glyph upward. Pixels above the level stay gray. The pixels at the level are the brighter gray, up to white. Gaps and the space above a letter stay dark. A dark-gray copy sits one cell down and one cell right and does not animate. The face stays opaque. Under it is a gap, then one status row, then the page, a gap, and the footer `↑↓ move · enter select · esc back · click` at the bottom. The status row is one line: a quiet rule, the selected model, the settings that are on, and the doctor summary. OK is green. A problem uses the existing red. Info stays plain. The row is not a slash path and it is not a menu item. When the page does not fit, that region scrolls. The wordmark and the status row stay on screen. History, logs, and doctor stay in the page and do not move the hero. Home header is `/digivoice`; the rows are `/history`, `/settings`, `/system`, and `/quit`. The current path has a one-cell left rule and a quiet row background. Other rows keep that cell blank, so the path text does not shift. Hover paints the same bar. A click is mouse up and runs the same action as Enter. Gray text on that same row is only the value or status, and a long value ellipsizes in the middle on one line. The page fades in on a path change. The wordmark does not. Settings header is the screen path (`/settings`, `/settings/speech`). The frame is a fixed width, centered in the terminal, so the wordmark stays centered and does not jump when the menu changes. The page is left-aligned in that frame and sits above the footer. A hotkey row shows an input only while capturing. The moment the placeholder `input new hotkey` is showing, digivoice writes `hotkey.capture` and its own hotkeys stop. The event tap passes that key through to the terminal, so Option, Command, and the other binds do not start dictation, speak, cancel, or the banner. Enter, Esc, or leaving the field removes the flag and arms the hotkeys again. Focus shows the cursor. Enter is the only save. Blur does not write. A physical Option press fills it with Left Option or Right Option (Right Option when the event does not say which side). The words `option` and `alt` are Right Option. Enter locks the binding into `hotkey_bindings`, reloads Hammerspoon the same way System Reload does, and returns to that row. Esc cancels and keeps the previous binding. A name that is not a key keeps that binding, warns, and is not written. A binding another role already uses is refused the same way: `settings.json` is not written, and the pane names that role. Saving the role's current binding is still allowed. Leaving `/settings` or any child writes `settings.json` before the screen changes. System header is `/system`; the rows are `/doctor`, `/reload`, `/reset`, `/restart`, `/update`, and `/logs`. History header is `/digivoice/history`. The takes sit in a scroll box stuck to the newest line; scrolling up pauses that pin until the bottom is visible again. The timestamp is the path, the transcript is gray on that row and stays selectable, and there is no copy button on the list. Enter shows the full text, Copy confirms on screen, and Delete returns to the list. Logs header is `/system/logs`: one line each, Enter shows the full line and any metadata, and an empty log is not a selectable row. Doctor is the word `doctor`: a short name, a few words, and a status. OK is green. Info stays plain. Reload, reset, restart, and update paint a loading state in the page first. Reload ends on a done line. Reset returns home. Restart re-execs the process. Update shows progress in the page, then restarts when the refresh did not fail. Esc on home exits 0 and leaves Hammerspoon running. `SIGHUP` does the same. Quit is the action that stops Hammerspoon. A click runs the same action as Enter, including a settings choice. Speech, voice, and rewrite model lists mark a file on disk with ↓ at the right edge of the row. The path stays left-aligned. `auto` is selectable and has no arrow. Choosing a model that is not on disk opens a download page in the pane: the model name, a progress bar, and a percentage that advances while bytes arrive. The hero and the footer stay. Success returns to that list on the same row, now with ↓. Failure stays on the page with the error and does not mark the model downloaded. Esc returns to the list and deletes only the partial. Choosing a model already on disk selects it and stays on that row. Other choices still return to the parent, which stays on the opened row. The OpenTUI process reads screens from `python -m digivoice.tui_bridge` (stdin JSON, no socket). A download is that same process, one JSON object per line. Pipes and agents stay on the Python CLI. The OpenTUI check is `npm test` in `digivoice/tui`, which runs `bun test` and `createTestRenderer` from `@opentui/core/testing`.

## Data locations

macOS defaults:

- models: `~/Library/Application Support/digivoice/models/`
- recordings: `~/Library/Application Support/digivoice/recordings/`
- history: `~/Library/Application Support/digivoice/history.jsonl`
- toggle stop-file: `~/Library/Application Support/digivoice/dict.stop`
- cancel-file: `~/Library/Application Support/digivoice/dict.cancel`
- banner status feed: `~/Library/Application Support/digivoice/status.json`
- banner spawn flag: `~/Library/Application Support/digivoice/banner.show`
- banner drag position: `~/Library/Application Support/digivoice/banner_pos.json`
- settings: `~/Library/Application Support/digivoice/settings.json`
- default model file: `~/Library/Application Support/digivoice/models/ggml-base.en.bin`

Linux fallback (also what `doctor` prints when reporting the other platform):

- models: `${XDG_DATA_HOME:-~/.local/share}/digivoice/models/`
- recordings: `${XDG_DATA_HOME:-~/.local/share}/digivoice/recordings/`
- history: `${XDG_DATA_HOME:-~/.local/share}/digivoice/history.jsonl`
- toggle stop-file: `${XDG_DATA_HOME:-~/.local/share}/digivoice/dict.stop`
- cancel-file: `${XDG_DATA_HOME:-~/.local/share}/digivoice/dict.cancel`
- banner status feed: `${XDG_DATA_HOME:-~/.local/share}/digivoice/status.json`
- banner spawn flag: `${XDG_DATA_HOME:-~/.local/share}/digivoice/banner.show`
- banner drag position: `${XDG_DATA_HOME:-~/.local/share}/digivoice/banner_pos.json`
- settings: `${XDG_DATA_HOME:-~/.local/share}/digivoice/settings.json`
- same filename: `ggml-base.en.bin`

`DIGIVOICE_DATA_DIR` overrides the data directory on every platform. `DIGIVOICE_PIPER_VOICE`
points at a Piper `.onnx` voice; otherwise `speak` uses the first `*.onnx` under the models
directory. `doctor` does not create directories; `dict`, `speak`, and `history` do, because those
commands write.

`ggml-base.en` is the snappy push-to-talk default. whisper.cpp ships that model as
`ggml-base.en.bin`.

## CLI

| Command | Exit | Behavior |
| --- | --- | --- |
| `doctor` | 0 ready, 1 not ready | Report below. A TTY opens the doctor screen. `digivoice /doctor` is the same command. |
| `dict [--hold\|--toggle] [--seconds N] [--stop-file PATH] [--cancel-file PATH] [--no-paste] [--no-rewrite]` | 0 dictated, 1 capture / transcribe failed or nothing recognized, 3 cancelled | Record, transcribe, optional rewrite, append, paste. |
| `speak [text\|--clipboard\|--selection\|--clipboard-or-history]` | 0 spoken, 1 Piper/player/source failed | Piper playback; append `kind:speak`. |
| `history [--last N] [--grep PATTERN] [--copy-last] [--json]` | 0 (1 if copy-last empty) | Lists / copies last dict. A TTY with no flags opens the history pages. `digivoice history --json` prints entries and does not open the TUI. |
| `cancel [--cancel-file PATH]` | 0 | Create the cancel-file; a running `dict` discards its take. |
| `status` | 0 shown, 1 none yet | Print the `status.json` the banner reads. |
| `banner show [--text T]` / `hide` / `toggle` | 0 | Write the `banner.show` spawn flag the adapter polls; shows a preview without dictation. |
| `settings` / `setup` [`get`/`set`/`path`] [`--json`] | 0 / 2 | `settings` shows or changes settings.json. `digivoice settings get KEY` and `digivoice settings set KEY VALUE` print or save and never open the TUI. An unknown key exits 2 and does not write settings.json. `setup` on a TTY opens the `/settings` path (speech, rewrite, banner, hotkeys). Enter opens a folder or a chooser. It does not toggle or cycle in place. On/off, pin, position, animations, style, model, voice, speed, and timeout each open a list; the value is saved only when that row is picked. After a choice or cancel, the parent stays on the row that was opened, including when that row was clicked. Esc goes up. Every screen shows `↑↓ move · enter select · esc back · click`. Left and right change page only when the screen has another page; previous and next are clickable. On home, Esc returns without stopping Hammerspoon. Speech model, Piper voice, reading speed, and the rewrite model each open a chooser on the saved row. A file on disk shows ↓ at the right of that row, including a catalog file under LM Studio, Ollama, or MLX, and selecting it saves the choice without fetching again. A missing catalog file opens a download page in the pane (name, bar, percentage). Success returns to that row with ↓. Failure stays with the error. Esc drops the partial and does not mark the model downloaded. A click stays inside that list. Hotkeys: Enter a row, press the key (modifiers included) or type its name (`Right Option`, `Esc`, `ctrl+shift+space`); Enter saves a typed name into `hotkey_bindings` when it is a key (Esc cancels that row only; a name that is not a key warns and is not written; a name another role already uses is refused and the pane names that role). While the field is open the adapter passes keys through. The Hammerspoon adapter reads those binds. Model rows show the English or multilingual description once and the model id once. `--print` or `DIGIVOICE_SETUP_NONINTERACTIVE=1` still prints the section menu with no prompts (exit 0, also when stdin is not a TTY); `--json` dumps settings + that menu + hardware stub. Detection flags (`word_detection`, `spelling_detection`) default off; stubs only, not wired to STT yet. Rewrite timeout is off by default. The chooser offers off, 15, 30, or 60 only. Post-process and STT menus offer a suggested local catalog. The numbered menu confirms, then downloads and wires the file. The OpenTUI list opens a download page for a missing file. No user-hosted / cloud endpoints. |
| `quit` | 0 | Stop the adapter and quit Hammerspoon. This is the full stop. Esc and closing the terminal do not call it. `digivoice /quit` is the same command. |
| `reset` | 0 | Restore settings defaults. History and models stay. `digivoice /reset` is the same command. |
| `restart` | 0 | Stop Hammerspoon, then replace this process with a fresh digivoice. The OpenTUI replacement calls libSystem on macOS and libc on Linux. If that call cannot run, the same command is started and this process waits for it. |
| `system` | 0 | TTY: Doctor, Reload, Reset, Restart, Update, Logs (`/system/logs`). Otherwise print those slash paths. Logs shows the whole `system.log` in the data directory (beside `status.json`). A take appends one line when it reaches `error` or `empty`. A missing file stays on the page as "No log yet". Reset confirm is still the first choice on that dialog. `digivoice /system/logs` on a TTY still opens that screen. |
| `logs` | 0 | Print the whole `system.log`. Never opens the TUI, including when stdin is a TTY. A missing or empty file prints `No log yet`. |
| `install` | 0 every step present or installed, 1 any step failed, 0 cancelled | On a terminal, a wizard: auto fetches bun 1.4.2, `bun install` `@opentui/core` in `digivoice/tui`, whisper-cli, Piper, sox, macOS espeak-ng when `libespeak-ng.1.dylib` is missing, `ggml-base.en.bin`, and `en_US-lessac-medium`, then copies the Hammerspoon lua into `~/.hammerspoon/digivoice` and `hs.reload()`. Pick downloads the chosen local speech, voice, and rewrite catalog files plus that same toolchain, and does not delete models already on disk. A pipe, `--auto`, or `DIGIVOICE_INSTALL_NONINTERACTIVE` skips the wizard and installs the auto set. A failed step does not stop the rest. Blank cancels before any fetch. No cloud STT/TTS. |
| `update` | 0 every step present or installed, 1 any step failed | Same steps as `install` with refresh. A step already at its pin stays. A missing or older step is fetched again. The adapter is copied either way, then `hs.reload()`. The TUI shows that report in the page, then restarts only when the bridge says the update is ok. A failure, including one whose note does not contain the word failed, stays in the page. |
| `uninstall` | 0 | Thin stub: not wired yet (remove the tool install and the data dir manually). |
| `reload [--json]` | 0 refreshed, 1 settings invalid or Hammerspoon reload failed | Re-resolve CLI path, validate settings, check the installed Lua adapter (symlink realpath proves the tip), `hs -c hs.reload()` with an 8s timeout. A dropped Mach reply (`CFMessagePort: dropping corrupt reply Mach message`) is success. Timeout and any other non-zero exit clear stale `status.json`. `hs` absent is a skip, not an error. The OpenTUI page shows that report. A failed reload is the report, not the word reloaded. |
| bare `digivoice` (no args) | 0 | TTY: fullscreen home. Centered DIGIVOICE half-block wordmark (square pixels, 3×3 per glyph cell when the window can hold them, otherwise 2×2, otherwise 1×1; xterm cube grays or truecolor, block V) whose letter pixels rest in subdued gray and brighten from the bottom of each column as an uneven level rises and falls. Gaps stay dark. A still dark-gray shadow sits one cell down and one cell right. On a tall window the slot rests about one third of the way down and shifts up when the window is short. A blank gap, then a status row (doctor summary; OK green, a problem red), then the page, which scrolls, then step-rail actions. The selected row has a one-cell left rule and a quiet background; other rows leave that cell blank. Home is History, Settings, System, Quit. Doctor is inside System. On macOS the same launch opens Hammerspoon if it is down (background-only: hide Dock icon, no digivoice menubar, no launch toast), loads `require("digivoice")` when the adapter is installed, and arms the banner (`M.ensure_banner` returns `armed`) without drawing it unless `banner_pinned` is true or a take is in progress. `live_banner` false skips the overlay. A running Hammerspoon is reloaded once when this launch added the require line, or when the loaded adapter has no `ensure_banner`; a take is never reloaded. Budget 4s; failure is a status line, not a hang. TUI Quit and `digivoice quit` stop the adapter and quit Hammerspoon. Esc and closing the Terminal leave it running. Every row is a block: action, then a gray shortcut, slash path, and metadata. Typing `/` runs that path (`/doctor`, `/settings/banner/pin`, `/quit`). History sticks to the newest line; the timestamp is the path and the text is gray on that row. Copy is `c` and Delete is `d`, or a click. Settings returns to home. No TTY: print the home overview (including that control line) and exit 0. `--help` / `-h` / `help` still show argparse help. |
| unknown / bad flags | 2 | Usage on stderr. |

## Agent commands

An agent uses this same `digivoice` binary. These commands never open the TUI, including when stdin is a TTY:

```bash
digivoice install --auto
digivoice settings get KEY
digivoice settings set KEY VALUE
digivoice logs
digivoice history --json
```

`digivoice install --auto` installs the auto toolchain with no wizard. `digivoice settings get KEY` prints one value. `digivoice settings set KEY VALUE` writes that key. An unknown key exits 2 and does not write `settings.json`. `digivoice logs` prints `system.log`. A missing or empty log prints `No log yet` and exits 0. `digivoice history --json` prints the entries as JSON. `digivoice /system/logs` on a TTY still opens the logs screen.

`--hold` and `--toggle` cannot be combined. `speak` takes text or exactly one of
`--clipboard` / `--selection` / `--clipboard-or-history`.

## Install

The documented install from a clone, at the repository root, is one command: `uv tool install --editable ./digivoice && export PATH="$HOME/.local/bin:$PATH" && digivoice install --auto`. It puts `digivoice` on `PATH`, runs the auto toolchain, reloads Hammerspoon, and exits. It does not open the wizard and it does not leave a TUI in the foreground. `digivoice install` on a terminal stays the wizard. `--auto`, a pipe, and `DIGIVOICE_INSTALL_NONINTERACTIVE=1` stay that same non-interactive auto path.

Once a GitHub release tag exists, that same `--auto` path installs the `digivoice` package (the name in `digivoice/pyproject.toml`) from the tag, not from a moving branch: `uv tool install --from "git+https://github.com/digithings-ai/digithings.git@<tag>#subdirectory=digivoice" digivoice && digivoice install --auto`. `<tag>` is the release tag. `subdirectory=digivoice` is required because the repository root is the workspace, not this package. The binary lands in `~/.local/bin`. This is not a PyPI install.

`digivoice install` brings in the local pieces required to run. On a terminal it is a wizard. Auto installs the current defaults only: the toolchain in the table below (bun, OpenTUI, whisper-cli, Piper, sox, macOS espeak-ng when `libespeak-ng.1.dylib` is missing, and the Hammerspoon adapter) plus `ggml-base.en.bin` and the Lessac voice `en_US-lessac-medium`. Auto does not download a rewrite GGUF. Pick asks for local speech, voice, and rewrite catalog files and downloads those. Models already on disk are left in place, including files the user did not choose. A pipe, `--auto`, or `DIGIVOICE_INSTALL_NONINTERACTIVE` skips the wizard and installs the auto set. `digivoice update` and System → Update (`/system/update`, also `/update`) always use that non-interactive path with refresh. macOS is the desktop this app runs on, because hotkeys and paste go through Hammerspoon. This command does not ship a Windows or Linux package for those hotkeys. It does not call a cloud STT or TTS service. Issue #4969 is the SHA-safe Hammerspoon adapter hold; it does not add an Otter model pack, and this command does not fetch Otter. Tests pass a fake `fetch` and a fake runner and a home under tmp. They do not download weights, they do not run this command against the network, and they do not write a real home directory.

Each step is `present`, `installed`, or `failed`. Later steps still run after a failure. The process exits 1 when any step failed. Archives that contain `..` or an absolute path are rejected. Tar extraction uses `filter="data"`.

A step that already exists is `present` and is not stamped. The versions this command itself writes live in `~/.local/share/digivoice/vendor/install.json`. Update re-fetches a step when its file is missing or that stamp differs from the pin. A matching stamp stays `present`. Sox that was already on `PATH` (stamp not `brew`) is left alone. Sox, macOS whisper-cli, or espeak-ng that this command installed with Homebrew is `brew upgrade` on update. espeak-ng is a macOS step: a same-arch `libespeak-ng.1.dylib` is copied beside the real Piper binary when one is already on the machine, and a missing one is `brew install espeak-ng`. A library of a different architecture is ignored. On an arm64 Mac, Homebrew's arm64 espeak-ng is not installed for an x86_64 Piper. Linux does not run that step. An arm64 Mac also replaces a vendor Piper whose Mach-O is x86_64, even when the version stamp still matches. On that Mac, install and update also place a same-arch `libpiper_phonemize.1.dylib` beside the real binary, plus the jar's arm64 `libespeak-ng.1.dylib` that exports `espeak_TextToPhonemesWithTerminator`. The dharmab archive does not contain the phonemize library, so a missing copy is fetched from piper-jni `1.2.0-a0f09cd`. That jar's `macos-arm64` member is thin Mach-O arm64. The same jar's `macos-amd64` member is Mach-O x86_64 and is not copied. Homebrew espeak-ng is not copied over the matching library.

The adapter step copies `init.lua`, `banner_core.lua`, `hotkeys.lua`, and any sibling `*.lua` from `digivoice/hammerspoon` into `~/.hammerspoon/digivoice`. A symlink that already points at this checkout is left in place. A real directory is replaced in place, and lua this checkout no longer ships is deleted, so an old copy or close control cannot remain. Then it runs `hs -c hs.reload()`, the same call as System Reload. `hs` absent is a skip, not an error. A non-zero exit that prints `CFMessagePort: dropping corrupt reply Mach message` is success (`hammerspoon .. reloaded`): reload tears the IPC down after the config has loaded. A timeout stays a failure. Any other failed reload marks the adapter step failed after the files are written.

| Step | Fresh install |
| --- | --- |
| bun | `bun` 1.4.2 zip into `~/.local/bin/bun`: `bun-darwin-aarch64`, `bun-darwin-x64`, `bun-linux-aarch64`, `bun-linux-x64` from `https://github.com/oven-sh/bun/releases/download/bun-v1.4.2/`. |
| opentui | `bun install --cwd digivoice/tui` for `@opentui/core`. `install` is the bun subcommand; `--cwd` follows it. `package.json` has no install script. |
| whisper-cli | Linux: whisper.cpp `v1.9.2` `whisper-bin-ubuntu-x64.tar.gz` or `whisper-bin-ubuntu-arm64.tar.gz` from `https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.2/`, extracted under `~/.local/share/digivoice/vendor/whisper`, then `~/.local/bin/whisper-cli` points at that binary so the sibling libraries stay beside it. macOS has no official CLI build: `brew install whisper-cpp`. Missing Homebrew fails that step with that reason. |
| piper | Linux and Intel macOS: Piper `2023.11.14-2` (`piper_linux_x86_64`, `piper_linux_aarch64`, `piper_macos_x64`) from `https://github.com/rhasspy/piper/releases/download/2023.11.14-2/`. arm64 macOS: `piper_macos_aarch64.tar.gz` from `https://github.com/dharmab/piper/releases/download/2024.12.14.1-alpha2/`, because the `2023.11.14-2` file of that name is Mach-O x86_64. Extracted under `vendor/piper`, with `~/.local/bin/piper` pointing at the binary. Update on an arm64 Mac replaces a vendor binary that is still x86_64. |
| espeak | macOS only. On an arm64 Mac the copy beside the real Piper binary is the piper-jni `macos-arm64` `libespeak-ng.1.dylib`, which is Mach-O arm64 and exports `espeak_TextToPhonemesWithTerminator`. A Homebrew espeak-ng already beside the binary does not export that symbol and is replaced. Homebrew is not copied over a library that has the symbol. An x86_64 espeak is not copied. On Intel, a same-arch library already beside the binary wins; otherwise Homebrew is copied there. Linux does not run this step. |
| phonemize | arm64 macOS only. `libpiper_phonemize.1.dylib` and `libonnxruntime.1.14.1.dylib` are copied beside the real Piper binary (`vendor/piper/piper/`, the directory dyld searches). A same-arch copy already there, or under another path in the Piper archive, is used. The dharmab `piper_macos_aarch64.tar.gz` does not contain `libpiper_phonemize.1.dylib`, so a missing library is fetched from piper-jni `1.2.0-a0f09cd` (`piper-jni-1.2.0-a0f09cd.jar`). That jar's `macos-arm64` member is thin Mach-O arm64 and includes `libespeak-ng.1.dylib` with `espeak_TextToPhonemesWithTerminator`. The same filenames under `macos-amd64` are Mach-O x86_64. Install copies the member whose Mach-O cpu matches Piper, not the first file of that name. An x86_64 library is not copied. Linux and Intel macOS do not run this step. |
| sox | Already on `PATH`, otherwise `brew install sox`. Missing Homebrew fails that step. |
| stt | `ggml-base.en.bin` from `https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin` into the models directory. |
| voice | `en_US-lessac-medium.onnx` and `en_US-lessac-medium.onnx.json` from `https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/`. |
| adapter | Current `digivoice/hammerspoon/*.lua` into `~/.hammerspoon/digivoice`, then `hs.reload()`. The overlay stays the status icon only: no copy, no close, no pin button. It retracts when idle or pending. |

## dict

1. **Capture** (`capture.py`). `sox` if it is on `PATH`, otherwise `ffmpeg`. 16 kHz mono
   16-bit, which is what whisper.cpp wants, so nothing has to resample. The file is
   `recordings/dict-<UTC stamp>-<8 hex>.wav`.
2. **Transcribe** (`transcribe.py`). `whisper-cli` (or the `whisper-cpp` alias) with
   `-m <model> -f <wav> -l en -nt` (multilingual catalog models use `-l auto`). The
   model is the saved `stt_model` (default `ggml-base.en` when nothing is saved):
   the weights under `models_dir`, an absolute path
   (that file, not a same-named file under `models_dir`), or the same filename already
   installed under LM Studio, Ollama (`OLLAMA_MODELS`), or MLX Studio (case does not
   matter). A missing file raises `model <id> is not installed locally: <path>`,
   the take exits 1, and that line is appended to `system.log`. stdout is the transcript;
   the banner chatter goes to stderr. Segment timestamps are stripped and whitespace is
   collapsed into one line.
3. **Rewrite** (`rewrite.py`, optional). When `rewrite_enabled`: local llama.cpp (or
   local ollama) lightly cleans the dictated words. The dictation is source text,
   never a brief to write something new. Context (email, SMS, professional, coding,
   blog, or none) is a formatting guide and a hint for a misspoken word. It does
   not add sentences, explanations, or extra context. Grammar and spelling stay
   light. Coding formats code or technical prose already dictated and does not
   invent code, APIs, or an implementation. Email formats an email and does not
   invent a subject, recipients, or new points. SMS stays short and in the
   dictated words. The model is a local GGUF: a suggested catalog file under the models
   dir, or an absolute file already on disk. The download list adds whisper.cpp
   medium and large ggml files plus Qwen2.5 7B, Llama 3.2 3B, and Gemma 2 2B
   GGUF weights. The same chooser also lists runnable files discovered under
   `~/.lmstudio/models`, `~/.cache/lm-studio/models`, `~/.ollama/models`
   (or `OLLAMA_MODELS`), and `~/.mlxstudio/models` (MLX Studio, the app also
   called MX Studio). Safetensors and an Ollama tag whose blob is missing stay
   out. URLs, OpenRouter, and ollama registry tags are rejected. Setup lists
   the catalog. The numbered menu confirms, then downloads and wires the file. The OpenTUI chooser opens a download page when that file is missing. A copy of the catalog filename under an install root is not missing. The chooser opens on the saved row. Selecting a discovered
   file stores that path. Auto-route from the focused app when enabled
   (match table is `rewrite_app_routes` in settings). Timeout is off by
   default. The settings chooser offers off, 15, 30, or 60 seconds only. Fail soft —
   raw transcript on error. Disabled by default. `--no-rewrite` skips.
4. **History** (`history.py`). One JSON object appended to `history.jsonl` (rewritten text when applied).
5. **Paste** (`paste.py`). darwin only, and never fatal. Skipped when `paste_on_stop` is false. When it is on, the transcript is copied with `pbcopy` and Command-V is sent to the app that had focus when the take started (`--focus-name` / `--focus-bundle`, or the frontmost process captured before recording). `osascript -e` receives that bundle id and name as the script argv. A leading `-` is not passed: with `-e` it is not an end-of-options mark, and it used to become the bundle id so the keystroke missed the app. Speak `--selection` uses that same argv when it reads the captured app's selected text, and the Cmd+C fallback activates that app before the keystroke.

Recording modes:

| Mode | Cap | Early stop |
| --- | --- | --- |
| `--hold` | 15s | No — self-bounding `trim` / `-t`. |
| `--toggle` | 30min safety (no UX limit) | Yes — stop-file (default `{data_dir}/dict.stop`), SIGINT/SIGTERM, or ~10s silence pause (sox). |
| neither | 30s | No. |

`--seconds N` overrides the cap. Hold / default use the bounded `CommandRunner` path.
Toggle with the real runner uses `Popen`: open-ended sox/ffmpeg, poll for the stop-file or
signal, SIGINT the recorder process group so the wav header stays valid, then continue the
pipeline. Injected fake runners keep the bounded path so unit tests need no signals.

**Failure behavior.** Missing `sox` and `ffmpeg`, a locked-down microphone, a missing
`ggml-base.en.bin`, a whisper failure, and silence are all exit 1 with a one-line message on
stderr — never a hang. A failed capture leaves nothing behind. A failed transcribe keeps the
wav and prints where it is. Nothing is appended to history for either, so silence never
becomes an empty entry.

**Interrupt / early stop.** Toggle stop (stop-file or signal) keeps the recorded wav, continues whisper → optional rewrite → history → paste of what was captured. Resume-same-take is not supported; expectation is **paste + new take**.

### Cancel (Esc) and empty-take discard

A take can end three ways without producing text, and none of them leaves anything behind:

| Outcome | Trigger | Exit | wav | history | paste | status |
| --- | --- | --- | --- | --- | --- | --- |
| cancelled | cancel-file appears (Esc in the Hammerspoon adapter, or `digivoice cancel`) | 3 | deleted | none | none | `cancelled` |
| empty | whisper returns nothing, or only a silence marker (`[BLANK_AUDIO]`, `[ Silence ]`, `(silence)`), or the final text is blank | 1 | deleted | none | none | `empty` |
| failed | missing tool, whisper error, permission denied | 1 | kept (transcribe failure) | none | none | `error` |

`dict` clears any stale cancel-file at start and again on exit, so a late Esc never kills the next take. The cancel-file is checked while the recorder runs (the recorder process group is signalled and the wav deleted), while `whisper-cli` / the rewrite model run (the real runner polls and kills the child), and between stages. The last check is immediately before the history append; once the history line is written the take is committed and a late cancel is ignored. `paste` / `copy_to_clipboard` also refuse blank text as a last line of defence. Cancelling mid-recording needs `--toggle` (the open-ended recorder, which is what the adapter runs). With `--hold` / default the recorder is bounded and cannot be interrupted, so the cancel lands when it finishes.

## Status feed (banner)

`dict` and `speak` write `status.json` (atomic replace) as they move through stages. The Hammerspoon banner polls it. It is display only. Fails soft: an unwritable file never changes the exit code. Skipped entirely when `live_banner` is false. `banner show [--text T]` / `hide` / `toggle` writes the `banner.show` spawn flag the adapter polls about once a second; a visible flag reveals a preview banner with no dictation behind it.

```json
{"session":"1a2b3c4d5e6f","kind":"dict","state":"rewriting","text":"hey ship the notes","detail":"preset email","updated_ms":1790000000000,"pid":4242}
```

`kind` is `dict` or `speak`. `state` is one of `loading`, `recording`, `transcribing`, `rewriting`, `pasting`, `speaking`, `done`, `cancelled`, `empty`, `error`. `text` is the transcript (dict: raw while transcribing/rewriting, final once pasting), the selected text (speak), or the finished text (`done`). `detail` is the rewrite preset, the paste result, or the error line. `updated_ms` is epoch milliseconds; the adapter ignores any snapshot older than its own session start. Live streaming STT is out of scope: the transcript appears after whisper returns.

**stdout is the transcript and nothing else**, so `digivoice dict | pbcopy` works. Progress,
the wav path, the paste result, and the history path all go to stderr.

## speak

1. **Resolve text.** Argv words, or `--clipboard` (`pbpaste` / `wl-paste` / `xclip` / `xsel`),
   or `--selection` (macOS, in order: focused element's Accessibility selected
   text in the captured app when `--focus-name` / `--focus-bundle` is set, else the
   frontmost app; then Ghostty's selection pasteboard when that target is Ghostty;
   then Cmd+C via osascript. Option is released, then a short pause, then a plain
   Command-C to the captured process. When `pbcopy` is available a private marker
   is written first. The clipboard is read again until it differs from that
   marker or a few brief retries run out. The first read is often still the
   marker, because the keystroke returns before the app copies. A later read that
   differs is the selection, including a selection that was already on the
   clipboard. The marker is never spoken. If every read is still the marker,
   nothing was selected: the previous clipboard is restored and is not spoken,
   and the error names the captured app and bundle. Accessibility text is used
   as soon as it is returned and does not require the clipboard to change.
   Without `pbcopy`, the copy counts only when the clipboard changes. A captured
   app is activated before that Command-C, with the same argv rule as paste: no
   leading dash. Linux: primary),
   or `--clipboard-or-history` (clipboard only; **no** history fallback — not the hotkey path).
   Hammerspoon speak uses `--selection`.
2. **Piper** (`speak.py`). `piper --model <voice.onnx> --output_file <speak-…wav>` with text
   on stdin. A saved `tts_voice` file on disk wins, including when `DIGIVOICE_PIPER_VOICE`
   points at a missing default. The env path is used when no saved file exists and that
   path exists. Otherwise the first `*.onnx` under models. The take errors only when no
   voice file can be found. On macOS the Piper build looks for `@rpath/libespeak-ng.1.dylib`,
   `@rpath/libpiper_phonemize.1.dylib`, and `@rpath/libonnxruntime.1.14.1.dylib`.
   speak sets `DYLD_LIBRARY_PATH`
   to the directory of a `libespeak-ng.1.dylib` whose Mach-O cpu matches the Piper binary.
   That is the real binary's directory, so the phonemize and onnxruntime libraries install
   places beside it are found there too.
   A library of a different architecture is not added. A same-arch library already beside
   the real binary wins, so an x86_64 Piper is not pointed at Homebrew's arm64 library.
   When `espeak-ng-data` contains `phontab`, speak passes `--espeak_data` so the
   `~/.local/bin/piper` symlink does not hide the data bundled next to the real binary.
   Saved `tts_speed` (`settings.json`, default `1`) is playback speed: `0.5`, `0.75`,
   `1`, `1.25`, `1.5`, `1.75`, or `2`. Piper's phoneme length is `1 / tts_speed`
   (`--length_scale`; smaller is faster). `1` omits the flag. `2` passes `0.5`. `0.5` passes `2`.
3. **Play.** `afplay` on darwin; `aplay` then `ffplay` on Linux. The player is its own
   session. `speak.stop` in the data directory is polled while Piper or the player runs;
   the player process group is then SIGKILLed. Exit 3, no history line. Killing only the
   digivoice pid would leave `afplay` running, so the stop is the process group, not a status flag.
4. **History.** Append `{kind:"speak", text, wav:null}` when playback finishes. A stop does not append.

### `--selection` path per app (macOS)

| Frontmost app | Step 1: AX selected text | Step 2: Ghostty pasteboard | Step 3: Cmd+C change-detect |
| --- | --- | --- | --- |
| Ghostty | Miss (terminal grid exposes no `AXSelectedText`; osascript's `missing value` is filtered, never spoken) | **Hit** — `pbpaste -pboard com.mitchellh.ghostty.selection` (copy-on-select) | Fallback when the selection pasteboard is empty (otherwise never reached; general clipboard untouched) |
| TextEdit / Notes / Mail (NSText) | **Hit** — focused text view's `AXSelectedText` in the captured app | Skipped (not Ghostty) | Fallback: release Option, then Command-C to that process |
| Safari / Chrome | Hit in text fields; miss on page content | Skipped | **Hit** — release Option, then Command-C to that process |
| Grok Bot / other apps | Hit when a text field holds the selection | Skipped | **Hit** — release Option, then Command-C to that process |

Step 3 speaks the text Command-C wrote after the marker, not whatever was already
on the clipboard. Option is released, then Command-C is sent to the captured
process. The clipboard is read more than once: the keystroke returns before the
app copies, so an early read can still be the marker, and a later read that
differs is the selection. A clipboard that stays the marker is empty selection:
the previous clipboard is put back and is not spoken, and the error names that
app. Leftover dictation or coding replies are not spoken, and no `kind:dict`
history is consulted. Every step fails soft to the next; all three empty is exit 1.

stdout is the spoken text. Missing piper, voice, player, or empty selection → exit 1,
one line on stderr. Hotkey (`--selection`) soft-fails when nothing is selected — never
falls back to clipboard or `kind:dict` history.

## Paste

darwin only. The transcript is copied to the clipboard with `pbcopy` over stdin — never
interpolated into an AppleScript string — and then `osascript` sends
`keystroke "v" using command down`. When focus is known, the script argv is the
bundle id then the app name. `osascript -e` does not treat a later `-` as the
end of options, so that dash is not passed. It used to be AppleScript argv item
1, the bundle lookup missed, and Command-V never reached the focused app.

The keystroke is the step that needs the macOS Accessibility grant. When it is denied, or
`pbcopy` / `osascript` are missing, or the platform is not darwin, `dict` still exits 0 with
the transcript on stdout and a note on stderr. `pbcopy` leaves the transcript in the
clipboard either way, which is the manual fallback.

## Doctor checks

Required for exit 0:

| id | Ready when |
| --- | --- |
| `whisper-cli` | `whisper-cli` or the `whisper-cpp` alias on `PATH`, otherwise `~/.local/bin/whisper-cli` |
| `piper` | Executable on `PATH`, otherwise `~/.local/bin/piper` |
| `capture` | `sox` or `ffmpeg` on `PATH` |
| `models` | Models directory exists and contains the configured STT file (default `ggml-base.en.bin`) |

Always informational:

| id | Meaning |
| --- | --- |
| `sox`, `ffmpeg` | Each binary, so a missing one is visible when the other satisfies `capture` |
| `settings` | `ok` when settings.json parses and validates (reports banner pin and position); `info` when absent (defaults); `missing` when corrupt. A leftover `banner_density` still loads and is ignored. |
| `hotkeys` | `ok` — defaults are Right Option / Esc / double-tap Left Option until `settings.json` `hotkey_bindings` replaces a row; see `hammerspoon/README.md` |
| `hammerspoon` | `ok` when the adapter dir/init.lua exists under `~/.hammerspoon/digivoice` or the data-dir hammerspoon path; `missing` otherwise |
| `history` | JSONL path and whether the file exists |
| `paths` | Active data directory, macOS models path, Linux models path, recordings directory |
| `tcc` | Mic and Accessibility are not probed; see `hammerspoon/README.md` |
| `rewrite` | Disabled by default (info). Names the configured local GGUF (default `qwen2.5-1.5b-instruct-q4_k_m.gguf`) and reports when that file is not installed. When rewrite is enabled: ok if local runner+GGUF ready, else missing (dict still uses raw transcript). The pass preserves the dictated words; context is format only. Cloud / URL models are not a doctor path. Setup → Post-process lists suggested local GGUFs (download + wire). |
| `detection` | Always info (never required). `word_detection` / `spelling_detection` default off; stubs only, STT still uses whisper |
| `interrupt` | Documents paste-on-stop + new-take behavior, and Esc / `digivoice cancel` discard |

## History records

One JSON object per line:

```json
{"ts":"2026-09-30T12:00:00.000Z","kind":"dict","text":"…","wav":"/…/recordings/dict-20260930T120000Z-1a2b3c4d.wav"}
{"ts":"2026-09-30T12:00:01.000Z","kind":"speak","text":"…","wav":null}
```

`ts` is ISO-8601 UTC with milliseconds and a `Z` suffix. `kind` is `dict` or `speak`.
`wav` is the recording path for dictation and `null` for speak (and when dictation has none).

Takes only append. The history screen may delete one line by rewriting the file;
unreadable lines stay. Reads skip lines that do not parse and report how many
were skipped rather than failing the listing. `--grep` matches the entry text
case-insensitively and applies before `--last`, so `--last 5 --grep invoice` is the last five
matching entries. A missing history file is not an error: `history` prints that and exits 0.

## Hammerspoon sample

Under `digivoice/hammerspoon/` (not imported by the Python package):

- Hotkeys are `hotkey_bindings` in `settings.json` (`dictation`, `speak`, `cancel`), parsed by `hammerspoon/hotkeys.lua`. Defaults are Right Option (61) → `dict --toggle --stop-file …`, double-tap Left Option (58) → `speak --selection`, and plain Esc → cancel. A saved remap replaces that bind; the old key is not also kept. The file is re-read when it changes (the next key uses the new bind) and on `hs.reload()` (`digivoice reload`). A binding that does not parse keeps the previous one, prints a warning, and does not stop the event tap. While `hotkey.capture` in the data directory is `1`, that tap returns the key to the terminal and does not run the bind. Enter, Esc, or leaving the field clears the file. A name another role already uses is not written. A custom canvas banner (5x5 square status grid) shows one status icon. No status word, copy, close, pin button, transcript, or fact line. Recording draws a level meter in that grid, and the bars keep rising and falling for the whole take. Loading and processing keep moving until that state ends. Dictating keeps moving while speech plays. The error, warning, and idle marks move in place. `banner_animations` false holds one frame. Each frame only updates cell fillColor. The icon phase is not a canvas attribute, and assigning it stops the frame timer. No digivoice menubar mark; background HS only (no Dock icon, no launch toast — TUI Quit tears HS down).
- The icon is the grid (equal 10px pad). Phases map from states the pipeline already sets: `recording`; `transcribing` draws dictating; `loading`, `rewriting`, `pasting`, and `speaking` draw processing; `error`; `warning`. Pending, idle, empty ("nothing to show"), and a finished take draw nothing. A pinned idle banner draws the idle mark, which breathes while animations are on. A `pending: true` flag hides the icon even when it is pinned. Chrome follows the system appearance: dark ground is the digiquant remock canvas (`#000`), light ground is the ivory paper (`#F9F8F6`); recording stays red and warning stays amber.
- The two visibility modes are the existing `banner_pinned` setting, chosen in the terminal UI. Off (the default) retracts for pending, idle, empty, and take end. On keeps the idle icon visible. Drag still moves the icon; release near one of the 9 anchors snaps and persists to `banner_pos.json`. The cancel bind still discards a take. There is no copy button and no close button.
- A click on the icon focuses the digivoice terminal when `tui.pid` shows it is already open, and opens it otherwise. The launcher is injected. Unit tests pass a fake and do not start Terminal or Hammerspoon. The click does not stack a new terminal.
- Launch arms Hammerspoon and draws the idle icon only when `banner_pinned` is true. Recording, dictating, processing, a current error, and a current warning draw the icon. `banner show` is a recording-icon preview unless `pending` is set. `banner hide` retracts it. `banner toggle` retracts while the preview is up and otherwise shows the recording icon. Take start and a `pending: true` flag hide the icon, including a pinned idle icon. Esc still discards a take.
- The cancel bind (Esc by default) writes the cancel-file while a dictation is recording/transcribing/rewriting (swallowed only then, unless the bind is a chord that must not also type). Nothing is pasted or saved.
- The speak bind (double-tap Left Option by default) runs `speak --selection` when nothing is playing (the banner shows the processing or error icon, not the selection; no clipboard/history). While that readout's task is still running, the same bind writes `speak.stop` and does not start another readout. The dictation bind writes that same file, waits until the speak task has exited, then starts dictation. Esc does not stop speech.
- No digivoice menubar mark and no Hammerspoon launch toast (background ship; TUI is chrome for customize / Quit).
- Banner settings (`live_banner`, `banner_position`, `banner_animations`, `banner_pinned`) are read from `settings.json` at the start of every take. `banner_pinned` decides whether the idle icon stays. `banner_animations` false holds one frame of the meter or mark. There is no density setting in the TUI or in `settings set`. A leftover `banner_density` in an old file still loads and is ignored.

See `hammerspoon/README.md` for install and Mic + Accessibility TCC.

## Out of this package

- Cloud STT/TTS or cloud rewrite backends
- OpenRouter / user-hosted URL rewrite models (blocked; post-process is local GGUF from the suggested catalog)
- Super Whisper
- A required OpenCode plugin
- Hammerspoon as a Python dependency (sample adapter only)
- Screen OCR
