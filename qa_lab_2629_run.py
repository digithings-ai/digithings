"""DIG-2629 lab: run every catalogued STT / rewrite / voice model on one sample set.

Evidence per row: model id, resolved weights path, the exact argv digivoice built,
wall-clock latency, and the output. Rows whose weights are absent are reported with
digivoice's own error string, never as a pass.

Isolation: DIGIVOICE_DATA_DIR points at a scratch dir whose models/ is a SYMLINK to
the real models dir, so weights resolve but recordings/history stay in scratch.
Nothing is downloaded. Nothing is written to Chris's real data dir.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from digivoice import catalog, paths, probe, runner, speak, transcribe
from digivoice import settings as settings_mod
from digivoice.settings import VoiceSettings

W = Path("/Users/chrisstefan/Code/digivoice-lab-dig2629")
SC = Path(
    "/private/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/"
    "paperclip-run-dig-2629-0f4dd87d-d07-IBYmNS"
)
REAL_MODELS = Path.home() / "Library/Application Support/digivoice/models"
OUT = SC / "lab" / "rows.jsonl"

# --- control: prove we are testing the pinned tree, not a sibling worktree -----
import digivoice  # noqa: E402

if not digivoice.__file__.startswith(str(W)):
    print(f"FATAL wrong tree: {digivoice.__file__}", file=sys.stderr)
    raise SystemExit(2)
print(f"CONTROL tree: {digivoice.__file__}", flush=True)

DATA = SC / "data"
(DATA / "recordings").mkdir(parents=True, exist_ok=True)
MODELS = DATA / "models"
# A previous run left a REAL EMPTY dir here, so the `if not exists()` guard
# silently skipped the symlink and every model read as absent. Assert instead.
if MODELS.is_symlink():
    MODELS.unlink()
elif MODELS.is_dir():
    if any(MODELS.iterdir()):
        print(f"FATAL {MODELS} is a real non-empty dir, refusing to touch", file=sys.stderr)
        raise SystemExit(2)
    MODELS.rmdir()
MODELS.symlink_to(REAL_MODELS)
assert MODELS.is_symlink(), "models dir is not a symlink"
assert (MODELS / "ggml-base.en.bin").is_file(), (
    "CONTROL FAILED: real weights not reachable through the scratch models dir"
)
print(f"CONTROL weights reachable: {(MODELS / 'ggml-base.en.bin').stat().st_size} B")

ENV = {
    "DIGIVOICE_DATA_DIR": str(DATA),
    "PATH": "/opt/homebrew/bin:"
    + str(Path.home() / ".local/bin")
    + ":/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    "HOME": str(Path.home()),
}
os.environ.update(ENV)

PATHS = paths.resolve_paths("darwin", Path.home(), ENV)
PR = probe.real_probe(ENV["PATH"])
RUN = runner.run_command
SETTINGS = VoiceSettings()
WAVS = sorted((SC / "wav").glob("*.wav"))

OUT.parent.mkdir(parents=True, exist_ok=True)
rows: list[dict] = []


def emit(row: dict) -> None:
    rows.append(row)
    with OUT.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.flush()
    print(json.dumps(row)[:400], flush=True)


def weights_status(path) -> tuple[bool, str]:
    p = Path(path)
    if p.is_file():
        return True, str(p.stat().st_size)
    return False, "absent"


print(f"\nCONTROL models_dir: {PATHS.models_dir} -> {Path(PATHS.models_dir).resolve()}")
print(f"CONTROL data_dir:   {PATHS.data_dir}")
print(f"CONTROL wavs:       {[w.name for w in WAVS]}")
print(f"CATALOG stt={len(catalog.STT_CATALOG)} "
      f"rewrite={len(catalog.REWRITE_CATALOG)} voice={len(catalog.VOICE_CATALOG)}\n")

# ============================ ARM 1 — STT ===================================
print("=== ARM 1: STT (whisper-cli) ===", flush=True)
for entry in catalog.STT_CATALOG:
    mid = entry.id
    mpath = transcribe.model_file(PATHS, mid, home=Path.home(), env=ENV)
    present, detail = weights_status(Path(mpath))
    if not present:
        emit({
            "arm": "stt", "model": mid, "status": "BLOCKED",
            "reason": "weights_not_installed",
            "missing_file": str(mpath),
            "size_hint": entry.size_hint,
            "command": None, "latency_s": None, "transcript": None,
        })
        continue
    for wav in WAVS:
        t0 = time.perf_counter()
        try:
            tr = transcribe.transcribe(
                PATHS, PR, RUN, str(wav), model_id=mid,
                home=Path.home(), env=ENV,
            )
            dt = time.perf_counter() - t0
            emit({
                "arm": "stt", "model": mid, "wav": wav.name, "status": "PASS",
                "weights_bytes": detail,
                "command": tr.argv,
                "latency_s": round(dt, 3),
                "transcript": tr.text,
                "transcribe_model": tr.model,
            })
        except Exception as exc:  # noqa: BLE001 - record the real failure
            dt = time.perf_counter() - t0
            emit({
                "arm": "stt", "model": mid, "wav": wav.name, "status": "FAIL",
                "weights_bytes": detail,
                "error_type": type(exc).__name__, "error": str(exc),
                "latency_s": round(dt, 3),
            })

# ============================ ARM 2 — REWRITE / LLM =========================
print("\n=== ARM 2: REWRITE (llama.cpp) ===", flush=True)
REWRITE_PROMPT_TEXT = (
    "hey can u pls add the meeting notes to the sprint board before friday thanks"
)
MODELS_DIR = Path(PATHS.models_dir)
for entry in catalog.REWRITE_CATALOG:
    fname = entry.filename
    mpath = MODELS_DIR / fname
    present, detail = weights_status(mpath)
    if not present:
        emit({
            "arm": "rewrite", "model": entry.id, "status": "BLOCKED",
            "reason": "weights_not_installed",
            "missing_file": str(mpath),
            "size_hint": entry.size_hint,
            "command": None, "latency_s": None, "output": None,
        })
        continue
    st = SETTINGS.model_copy(update={
        "rewrite_enabled": True,
        "rewrite_preset": "professional",
        "rewrite_model": fname,
        "rewrite_runner": "llama.cpp",
    })
    from digivoice import rewrite as rw

    t0 = time.perf_counter()
    try:
        r = rw.rewrite_transcript(
            REWRITE_PROMPT_TEXT, paths=PATHS, settings=st, probe=PR,
            runner=RUN, platform="darwin",
        )
        dt = time.perf_counter() - t0
        chosen = rw.pick_runner(PATHS, st, PR, RUN)
        emit({
            "arm": "rewrite", "model": entry.id, "status": "PASS",
            "weights_bytes": detail,
            "runner_selected": getattr(chosen, "name", None),
            "applied": r.applied, "preset": r.preset, "detail": r.detail,
            "input": REWRITE_PROMPT_TEXT, "output": r.text,
            "latency_s": round(dt, 3),
        })
    except Exception as exc:  # noqa: BLE001
        dt = time.perf_counter() - t0
        emit({
            "arm": "rewrite", "model": entry.id, "status": "FAIL",
            "weights_bytes": detail,
            "error_type": type(exc).__name__, "error": str(exc),
            "latency_s": round(dt, 3),
        })

# ============================ ARM 3 — VOICE / TTS ===========================
print("\n=== ARM 3: VOICE (piper + afplay) ===", flush=True)
TTS_TEXT = "Ship number forty two, on March third."
for entry in catalog.VOICE_CATALOG:
    vname = entry.filename
    vpath = MODELS_DIR / vname
    sidecar = MODELS_DIR / f"{vname}.json"
    present = vpath.is_file() and sidecar.is_file()
    if not present:
        emit({
            "arm": "voice", "model": entry.id, "status": "BLOCKED",
            "reason": "voice_not_installed",
            "missing_file": str(vpath),
            "sidecar_present": sidecar.is_file(),
            "command": None, "latency_s": None, "output": None,
        })
        continue
    # PIN this row's voice through the real persistence path, then ASSERT the voice
    # resolve_voice() actually picks matches the request BEFORE claiming a pass.
    # speak() reads tts_voice from settings.json on disk (speak.py:733 -> resolve_voice),
    # so an in-memory VoiceSettings alone is ignored, and resolve_voice() then falls
    # back to sorted(glob("*.onnx"))[0] -- which silently spoke the wrong voice for 2 of 3.
    settings_mod.save_settings(PATHS, VoiceSettings().model_copy(
        update={"tts_voice": vname}))
    chosen = speak.resolve_voice(PATHS, ENV, PR)
    if chosen.name != vname:
        emit({
            "arm": "voice", "model": entry.id, "status": "FAIL",
            "reason": "voice_not_honoured",
            "requested_voice": vname, "resolved_voice": str(chosen),
            "command": None, "latency_s": None, "output": None,
        })
        continue
    t0 = time.perf_counter()
    try:
        r = speak.speak(
            PATHS, PR, RUN, TTS_TEXT,
            platform="darwin", home=Path.home(), env=ENV,
        )
        dt = time.perf_counter() - t0
        wav_out = Path(r.wav_path) if r.wav_path else None
        emit({
            "arm": "voice", "model": entry.id, "status": "PASS",
            "voice_path": r.voice_path, "player": r.player,
            "wav_path": str(wav_out) if wav_out else None,
            "wav_bytes": wav_out.stat().st_size if wav_out and wav_out.is_file() else None,
            "command_piper": r.argv_piper, "command_play": r.argv_play,
            "input": TTS_TEXT, "output": r.text,
            "latency_s": round(dt, 3),
        })
    except Exception as exc:  # noqa: BLE001
        dt = time.perf_counter() - t0
        emit({
            "arm": "voice", "model": entry.id, "status": "FAIL",
            "error_type": type(exc).__name__, "error": str(exc),
            "latency_s": round(dt, 3),
        })

print(f"\nROWS WRITTEN: {len(rows)} -> {OUT}", flush=True)