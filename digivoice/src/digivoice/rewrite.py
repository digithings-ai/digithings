"""Optional post-STT rewrite with a local LLM only.

Runs after whisper and before history/paste. Disabled by default. Fail soft:
any runner/model/timeout error returns the raw transcript unchanged.

Pluggable runners: ollama CLI, llama.cpp (llama-cli / main), auto-detect.
Weights are not bundled — place a GGUF under the models dir or pull an Ollama
tag; doctor reports when rewrite is enabled but the runner/model is missing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from digivoice.models import CheckStatus, RewriteResult, VoicePaths
from digivoice.probe import CommandProbe
from digivoice.runner import CommandRunner, error_tail
from digivoice.settings import VoiceSettings

PRESET_PROMPTS: dict[str, str] = {
    "email": (
        "Rewrite the dictation as a clear professional email body. "
        "Keep the speaker's intent. Use short paragraphs. Do not add a subject line "
        "unless one is clearly dictated. No preamble."
    ),
    "sms": (
        "Rewrite as a short SMS/text message. Plain language, under ~300 characters "
        "when possible. No greeting/sign-off unless dictated. No preamble."
    ),
    "professional": (
        "Rewrite as a polished professional social post (LinkedIn/X). "
        "Keep facts, tighten tone, light structure. No hashtag spam. No preamble."
    ),
    "coding": (
        "Rewrite as a precise prompt for a coding agent (CLI / IDE agent). "
        "State the goal, constraints, and acceptance checks. Imperative voice. No preamble."
    ),
    "blog": (
        "Rewrite as readable blog prose. Light structure, keep the speaker's voice. "
        "No SEO filler. No preamble."
    ),
    "none": (
        "Lightly clean the dictation: fix obvious dictation artifacts and punctuation. "
        "Do not change meaning. No preamble."
    ),
}

REWRITE_TIMEOUT_DEFAULT = 30.0


class LocalRewriteRunner(Protocol):
    """Local-only rewrite backend. Implementations must not call cloud APIs."""

    name: str

    def available(self) -> bool: ...

    def rewrite(self, system: str, user: str, *, timeout: float) -> str: ...


class OllamaRewriteRunner:
    """Shells out to `ollama run <model>` with the prompt on stdin."""

    name = "ollama"

    def __init__(
        self,
        probe: CommandProbe,
        runner: CommandRunner,
        model: str,
    ) -> None:
        self._probe = probe
        self._runner = runner
        self._model = model

    def available(self) -> bool:
        return self._probe.lookup("ollama") is not None and bool(self._model)

    def rewrite(self, system: str, user: str, *, timeout: float) -> str:
        binary = self._probe.lookup("ollama")
        if not binary:
            raise RuntimeError("ollama not on PATH")
        prompt = f"{system}\n\nDictation:\n{user}\n\nRewritten text:"
        result = self._runner(
            [binary, "run", self._model],
            stdin=prompt,
            timeout=timeout,
        )
        if result.code != 0:
            reason = error_tail(result.stderr) or f"exit {result.code}"
            raise RuntimeError(f"ollama failed ({reason})")
        text = result.stdout.strip()
        if not text:
            raise RuntimeError("ollama returned empty rewrite")
        return text


class LlamaCppRewriteRunner:
    """Shells out to llama-cli / llama-completion with a local GGUF."""

    name = "llama.cpp"

    def __init__(
        self,
        probe: CommandProbe,
        runner: CommandRunner,
        model_path: str,
    ) -> None:
        self._probe = probe
        self._runner = runner
        self._model_path = model_path

    def _binary(self) -> str | None:
        for name in ("llama-cli", "llama-completion", "main"):
            found = self._probe.lookup(name)
            if found:
                return found
        return None

    def available(self) -> bool:
        if not self._model_path:
            return False
        if not self._probe.is_file(self._model_path):
            return False
        return self._binary() is not None

    def rewrite(self, system: str, user: str, *, timeout: float) -> str:
        binary = self._binary()
        if not binary:
            raise RuntimeError("llama-cli / llama-completion not on PATH")
        prompt = f"{system}\n\nDictation:\n{user}\n\nRewritten text:"
        argv = [
            binary,
            "-m",
            self._model_path,
            "-p",
            prompt,
            "-n",
            "512",
            "--no-display-prompt",
        ]
        result = self._runner(argv, timeout=timeout)
        if result.code != 0:
            reason = error_tail(result.stderr) or f"exit {result.code}"
            raise RuntimeError(f"llama.cpp failed ({reason})")
        text = result.stdout.strip()
        if not text:
            raise RuntimeError("llama.cpp returned empty rewrite")
        return text


def resolve_rewrite_model_path(paths: VoicePaths, settings: VoiceSettings) -> str | None:
    """Absolute GGUF path or Ollama tag. None when unset."""
    if settings.rewrite_model:
        candidate = Path(settings.rewrite_model).expanduser()
        if (
            candidate.is_absolute()
            or "/" in settings.rewrite_model
            or settings.rewrite_model.endswith((".gguf", ".bin"))
        ):
            # Prefer absolute / relative file paths under models dir.
            if not candidate.is_absolute():
                under = Path(paths.models_dir) / settings.rewrite_model
                return str(under)
            return str(candidate)
        # Bare ollama tag like "qwen2.5:3b".
        return settings.rewrite_model
    # Convention: first *.gguf under models/.
    models = Path(paths.models_dir)
    if models.is_dir():
        ggufs = sorted(models.glob("*.gguf"))
        if ggufs:
            return str(ggufs[0])
    return None


def pick_runner(
    paths: VoicePaths,
    settings: VoiceSettings,
    probe: CommandProbe,
    runner: CommandRunner,
) -> LocalRewriteRunner | None:
    model = resolve_rewrite_model_path(paths, settings)
    kind = settings.rewrite_runner
    if kind == "ollama":
        return OllamaRewriteRunner(probe, runner, model or "")
    if kind == "llama.cpp":
        path = (
            model if model and (model.endswith(".gguf") or Path(model).is_file()) else (model or "")
        )
        return LlamaCppRewriteRunner(probe, runner, path)
    # auto: prefer ollama when on PATH and model looks like a tag; else llama.cpp for GGUF.
    if model and not model.endswith(".gguf") and "/" not in model and probe.lookup("ollama"):
        return OllamaRewriteRunner(probe, runner, model)
    if model and (model.endswith(".gguf") or Path(model).is_file()):
        llama = LlamaCppRewriteRunner(probe, runner, model)
        if llama.available() or kind == "auto":
            return llama
    if probe.lookup("ollama") and model:
        return OllamaRewriteRunner(probe, runner, model)
    if model:
        return LlamaCppRewriteRunner(probe, runner, model)
    return None


def focused_app_name(
    platform: str,
    probe: CommandProbe,
    runner: CommandRunner,
) -> str | None:
    """Best-effort frontmost app name (darwin). None when unavailable."""
    if platform != "darwin":
        return None
    osascript = probe.lookup("osascript")
    if not osascript:
        return None
    script = 'tell application "System Events" to get name of first application process whose frontmost is true'
    result = runner([osascript, "-e", script], timeout=3.0)
    if result.code != 0:
        return None
    name = result.stdout.strip()
    return name or None


def preset_for_app(
    app_name: str | None,
    routes: dict[str, str] | None = None,
) -> str | None:
    """Match focused app name against config routes (substring, casefold).

    `routes` comes from settings.rewrite_app_routes — not a hard-coded path table.
    """
    if not app_name:
        return None
    table = routes or {}
    needle = app_name.casefold()
    # Longer fragments first so e.g. "imessage" wins over "message" if both exist.
    for fragment, preset in sorted(table.items(), key=lambda item: len(item[0]), reverse=True):
        if fragment.casefold() in needle:
            return preset
    return None


def resolve_preset(settings: VoiceSettings, app_name: str | None) -> str:
    if settings.rewrite_auto_route:
        routed = preset_for_app(app_name, settings.rewrite_app_routes)
        if routed:
            return routed
    return settings.rewrite_preset


def rewrite_transcript(
    text: str,
    *,
    paths: VoicePaths,
    settings: VoiceSettings,
    probe: CommandProbe,
    runner: CommandRunner,
    platform: str = "darwin",
    rewrite_runner: LocalRewriteRunner | None = None,
) -> RewriteResult:
    """Apply local rewrite or return the raw transcript. Never raises for soft fails."""
    raw = text
    if not settings.rewrite_enabled:
        return RewriteResult(
            text=raw,
            applied=False,
            preset=settings.rewrite_preset,
            detail="rewrite disabled",
        )
    stripped = raw.strip()
    if not stripped:
        return RewriteResult(
            text=raw,
            applied=False,
            preset=settings.rewrite_preset,
            detail="empty transcript",
        )
    app_name = None
    if settings.rewrite_auto_route:
        app_name = focused_app_name(platform, probe, runner)
    preset = resolve_preset(settings, app_name)
    system = PRESET_PROMPTS.get(preset, PRESET_PROMPTS["none"])
    local = rewrite_runner or pick_runner(paths, settings, probe, runner)
    if local is None or not local.available():
        return RewriteResult(
            text=raw,
            applied=False,
            preset=preset,
            detail="rewrite runner/model unavailable; using raw transcript",
            app_name=app_name,
        )
    timeout = float(settings.rewrite_timeout_seconds or REWRITE_TIMEOUT_DEFAULT)
    try:
        rewritten = local.rewrite(system, stripped, timeout=timeout)
    except Exception as exc:
        return RewriteResult(
            text=raw,
            applied=False,
            preset=preset,
            detail=f"rewrite failed ({exc}); using raw transcript",
            runner=local.name,
            app_name=app_name,
        )
    cleaned = rewritten.strip()
    if not cleaned:
        return RewriteResult(
            text=raw,
            applied=False,
            preset=preset,
            detail="rewrite empty; using raw transcript",
            runner=local.name,
            app_name=app_name,
        )
    return RewriteResult(
        text=cleaned,
        applied=True,
        preset=preset,
        detail=f"rewrote with {local.name} preset={preset}",
        runner=local.name,
        app_name=app_name,
    )


def rewrite_doctor_detail(
    paths: VoicePaths,
    settings: VoiceSettings,
    probe: CommandProbe,
    runner: CommandRunner,
) -> tuple[CheckStatus, str]:
    """Return (status, detail) for the informational doctor rewrite check.

    status is ok / missing / info. Never required for doctor exit 0.
    """
    model = resolve_rewrite_model_path(paths, settings)
    local = pick_runner(paths, settings, probe, runner)
    if not settings.rewrite_enabled:
        hint = model or f"no GGUF under {paths.models_dir} and rewrite_model unset"
        return (
            "info",
            f"disabled (default). model={hint}. enable with: digivoice settings set rewrite_enabled true",
        )
    if local is None or not local.available():
        return (
            "missing",
            (
                "enabled but runner/model not ready. Install ollama or llama-cli, "
                f"place a GGUF under {paths.models_dir}/ or set rewrite_model. "
                "dict still pastes the raw transcript."
            ),
        )
    return (
        "ok",
        f"enabled via {local.name}; model={model}; preset={settings.rewrite_preset}; "
        f"auto_route={settings.rewrite_auto_route}",
    )


# Re-export Mapping for type checkers that import from this module's callers.
__all__ = [
    "LocalRewriteRunner",
    "LlamaCppRewriteRunner",
    "OllamaRewriteRunner",
    "PRESET_PROMPTS",
    "focused_app_name",
    "pick_runner",
    "preset_for_app",
    "resolve_preset",
    "resolve_rewrite_model_path",
    "rewrite_doctor_detail",
    "rewrite_transcript",
]
