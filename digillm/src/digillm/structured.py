"""Structured (validated Pydantic) completions and mode-based model resolution.

:func:`structured_completion` wraps :func:`digillm.client.completion` with a
json_schema ``response_format`` derived from the target Pydantic model, then
strips any markdown fences the model emits and validates the JSON into an
instance. It mirrors twelve-x's ``call_structured`` but takes the model
explicitly (provider-agnostic; no hardcoded config file).

:func:`resolve_model` performs optional test/medium/best mode resolution from a
caller-supplied mapping or YAML path — digillm hardcodes no config location.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from digillm.client import ChatCompletionMessage, completion

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def structured_completion(
    model: str,
    messages: list[ChatCompletionMessage],
    output_type: type[T],
    *,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    strict: bool = True,
) -> T:
    """Call the LLM and return a validated instance of ``output_type``.

    Builds a json_schema ``response_format`` from ``output_type`` (via
    ``model_json_schema()``), calls :func:`completion`, strips markdown code
    fences that some providers wrap around JSON, narrows to the outermost
    ``{...}`` object, then validates with ``output_type.model_validate``.

    Args:
        model:       Model string (provider-prefix routing applies).
        messages:    OpenAI-style message list.
        output_type: Pydantic model class to validate and return.
        temperature: Sampling temperature.
        max_tokens:  Optional token cap.
        strict:      Sets the json_schema ``strict`` flag (OpenAI/Gemini honor it).

    Returns:
        A validated instance of ``output_type``.

    Raises:
        ValueError: when the model returns an empty response.
        pydantic.ValidationError: when the response fails schema validation.
        json.JSONDecodeError: when the response is not valid JSON.
    """
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": output_type.__name__,
            "schema": output_type.model_json_schema(),
            "strict": strict,
        },
    }
    logger.debug("structured_completion: model=%s output=%s", model, output_type.__name__)

    resp = completion(
        model,
        messages,
        temperature=temperature,
        response_format=response_format,  # type: ignore[arg-type]
        max_tokens=max_tokens,
    )
    raw = (resp.choices[0].message.content or "").strip() if resp.choices else ""

    if not raw:
        raise ValueError(f"Empty response from model {model!r} for {output_type.__name__}")

    # Strip markdown code fences some models emit around JSON — any language
    # token, any case (```json / ```JSON / ```application/json) and bare ```.
    if "```" in raw:
        raw = re.sub(r"```[A-Za-z0-9_./+-]*", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)

    return output_type.model_validate(json.loads(raw))


# ── Mode-based model resolution (opt-in) ────────────────────────────────────────

_VALID_MODES = ("test", "medium", "best")


def resolve_model(
    mode: str,
    modes: dict[str, str] | None = None,
    *,
    path: str | Path | None = None,
    default: str | None = None,
) -> str:
    """Resolve a ``test`` / ``medium`` / ``best`` mode to a concrete model string.

    Resolution is fully caller-driven — digillm hardcodes no config location.
    Provide either an explicit ``modes`` mapping or a YAML ``path`` whose top
    level is a ``mode -> model`` mapping (or contains a ``defaults:`` sub-mapping,
    matching DigiThings' ``model_modes.yaml`` shape). ``modes`` wins over ``path``.

    Args:
        mode:    Desired mode (case-insensitive); typically one of test/medium/best.
        modes:   Explicit ``{mode: model}`` mapping.
        path:    YAML file path used when ``modes`` is not given. Requires PyYAML
                 (install ``digillm[modes]``).
        default: Fallback model if ``mode`` is absent from the resolved mapping.

    Returns:
        The concrete model string for ``mode``.

    Raises:
        KeyError:     when ``mode`` is not found and no ``default`` is given.
        RuntimeError: when ``path`` is given but PyYAML is not installed.
    """
    table = modes if modes is not None else _load_modes_yaml(path)
    key = mode.lower().strip()
    if key in table:
        return table[key]
    if default is not None:
        return default
    raise KeyError(
        f"mode {mode!r} not found in modes mapping (have: {sorted(table)}) and no default given"
    )


def _load_modes_yaml(path: str | Path | None) -> dict[str, str]:
    """Load a ``mode -> model`` mapping from a YAML file (lazy PyYAML import)."""
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        logger.warning("model modes file not found: %s", p)
        return {}
    try:
        import yaml  # noqa: PLC0415 — lazy import; only the path branch needs PyYAML
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "resolve_model(path=...) requires PyYAML. Install with: pip install 'digillm[modes]'"
        ) from e
    with open(p) as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        return {}
    # Accept either a flat mapping or a nested ``defaults:`` mapping.
    defaults = raw.get("defaults")
    table = defaults if isinstance(defaults, dict) else raw
    return {str(k): str(v) for k, v in table.items() if k in _VALID_MODES}
