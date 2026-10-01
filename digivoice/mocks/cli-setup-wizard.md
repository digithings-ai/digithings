# DigiVoice `setup` wizard — CLI mock (CHR-860 / #4953)

ASCII/TTY mock of the interactive config spine. Pixel language: DigiVoice banner /
digithings.ai top bar (text only here). Agents use `digivoice setup --print` or
`DIGIVOICE_SETUP_NONINTERACTIVE=1` (no TTY).

## Entry

```
$ digivoice setup

┌─ digivoice setup ──────────────────────────────────────┐
│  DigiVoice · local speech config                       │
│  settings: ~/Library/Application Support/digivoice/…   │
│  ↑↓ move · Enter select · Esc back · q quit            │
└────────────────────────────────────────────────────────┘

  ▶ Models (STT / TTS / rewrite)
    Features (paste, banner)
    Hotkeys (docs)
    Hardware recommendations (#4939 hook)
    Review & save
    Doctor (run health checks)
    Quit
```

## Models screen

```
┌─ Models ───────────────────────────────────────────────┐
│  stt_model ............... ggml-base.en                 │
│  tts_voice ............... (auto / DIGIVOICE_PIPER_…)   │
│  rewrite_enabled ......... false                        │
│  rewrite_preset .......... none                         │
│  rewrite_model ........... (unset)                      │
│  rewrite_runner .......... auto                         │
│  rewrite_auto_route ...... false                        │
│  rewrite_timeout_seconds . 30.0                         │
└────────────────────────────────────────────────────────┘
  ▶ Edit stt_model
    Edit tts_voice
    Toggle rewrite_enabled
    …
    Back
```

Arrow + Enter edits one VoiceSettings field (same keys as `settings set`).

## Features screen

```
  paste_on_stop ...... true
  live_banner ........ true
  banner_position .... top-center   [↑↓ cycle literals]
  banner_density ..... peek         [mini | peek | full]
  banner_animations .. true
```

## Hotkeys (read-only docs)

```
  dict_toggle ...... Right Option — dict --toggle
  speak_selection .. Double-tap Left Option — speak --selection
  cancel ........... Esc — discard take
```

## Hardware recommendations (placeholder for #4939)

```
  recommend_models() → stub list by RAM / chip class
  "See epic #4939 / CHR-853 — catalog not rebuilt in this PR"
```

## Non-interactive / agent

```
$ digivoice setup --print
# prints current settings + wizard menu tree (no prompts); exit 0

$ DIGIVOICE_SETUP_NONINTERACTIVE=1 digivoice setup
# same as --print; for CI / Muse tests
```

`settings` / `settings get|set|path` unchanged. `setup` is NOT a mere alias that only prints settings.

## Doctor mock (strengthened)

```
$ digivoice doctor
digivoice doctor

[ok] whisper-cli  /opt/homebrew/bin/whisper-cli
[ok] piper        ~/.local/bin/piper
[ok] sox          /opt/homebrew/bin/sox
[missing] ffmpeg  not on PATH
[ok] capture      /opt/homebrew/bin/sox
[ok] models       ggml-base.en at …/models/ggml-base.en.bin
[ok] settings     valid settings.json (banner_density=peek)
[ok] hotkeys      sample binds documented (see hammerspoon/README)
[ok] hammerspoon  adapter at ~/.hammerspoon/digivoice (or App Support)
[info] history    …
[info] paths      …
[info] rewrite    disabled
[info] tcc        Mic/Accessibility not probed
[info] interrupt  …

result: ok
```

## Thin stubs

```
$ digivoice update
digivoice update: not wired yet — reinstall via uv / brew when available

$ digivoice uninstall
digivoice uninstall: not wired yet — remove uv tool + data dir manually
```
