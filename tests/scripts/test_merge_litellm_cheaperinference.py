"""Curated-model pins for the Cheaper Inference LiteLLM merge (DIG-4512).

The stack merges ``config/litellm.cheaperinference.yaml`` over the base file
at container boot. The base file the image actually ships
(``infra/digichat-release/config/litellm.yaml``) has 8 model_names and NONE of
them is a curated house model, so a merge that does not happen leaves every
curated tenant model unknown to LiteLLM while the health probe stays green.

These tests pin the loud failure: a merged model_list that is missing a
curated id must fail with the missing ids named, and must not leave an output
file behind.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
MERGE_SCRIPT = REPO_ROOT / "scripts" / "merge_litellm_cheaperinference.py"
# The base file the container image ships (Dockerfile COPY of
# infra/digichat-release/config into /app/config).
IMAGE_BASE = REPO_ROOT / "infra" / "digichat-release" / "config" / "litellm.yaml"
REPO_OVERLAY = REPO_ROOT / "config" / "litellm.cheaperinference.yaml"
# The curated house models, as the stack worker forwards them
# (wrangler.toml [vars] DIGI_SESSION_MODEL_ALLOWLIST).
CURATED_IDS = (
    "deepseek/deepseek-v4.1-flash",
    "z-ai/glm-5.3-flash",
    "qwen/qwen3.8-flash",
    "google/gemma-4-31b-it",
    "xiaomi/mimo-v2.6-flash",
    "z-ai/glm-4.7-flash",
)


def _run(*args: str, allowlist_env: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["DIGI_SESSION_MODEL_ALLOWLIST"] = "" if allowlist_env is None else allowlist_env
    return subprocess.run(
        [sys.executable, str(MERGE_SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _model_names(path: Path) -> set[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        entry["model_name"]
        for entry in data["model_list"]
        if isinstance(entry, dict) and isinstance(entry.get("model_name"), str)
    }


def _write_overlay(path: Path, model_name: str) -> None:
    path.write_text(
        "model_list:\n"
        f"  - model_name: {model_name}\n"
        "    litellm_params:\n"
        "      model: openai/some-model\n",
        encoding="utf-8",
    )


def test_image_base_carries_no_curated_model():
    """The reason the check exists: the shipped base file has no curated id."""
    assert not _model_names(IMAGE_BASE) & set(CURATED_IDS)
    assert len(_model_names(IMAGE_BASE)) == 8


def test_merge_of_the_real_assets_keeps_every_curated_id(tmp_path):
    """The real overlay must cover the whole curated set, or the check fires
    on a healthy image."""
    out = tmp_path / "litellm.runtime.yaml"
    result = _run(
        "--base",
        str(IMAGE_BASE),
        "--overlay",
        str(REPO_OVERLAY),
        "--allowlist",
        ",".join(CURATED_IDS),
        "--require-curated-ids",
        "-o",
        str(out),
    )
    assert result.returncode == 0, result.stderr
    assert out.is_file(), "the merged config was not written"
    assert set(CURATED_IDS) <= _model_names(out)


def test_missing_curated_ids_fail_loudly_and_write_no_file(tmp_path):
    """A merged model_list without the curated ids must fail, name the missing
    ids, and leave no output file behind."""
    overlay = tmp_path / "litellm.cheaperinference.yaml"
    _write_overlay(overlay, "some/other-model")
    out = tmp_path / "litellm.runtime.yaml"
    result = _run(
        "--base",
        str(IMAGE_BASE),
        "--overlay",
        str(overlay),
        "--allowlist",
        ",".join(CURATED_IDS),
        "--require-curated-ids",
        "-o",
        str(out),
    )
    assert result.returncode != 0, result.stdout
    assert "ERROR" in result.stderr, result.stderr
    for curated in CURATED_IDS:
        assert curated in result.stderr, f"{curated} is not named in {result.stderr!r}"
    assert not out.exists(), "a failed merge must not leave a config behind"


def test_allowlist_defaults_to_the_environment_variable(tmp_path):
    """The stack forwards the curated set as DIGI_SESSION_MODEL_ALLOWLIST, so
    the script must read it from the environment when no flag is given."""
    overlay = tmp_path / "litellm.cheaperinference.yaml"
    _write_overlay(overlay, "some/other-model")
    out = tmp_path / "litellm.runtime.yaml"
    result = _run(
        "--base",
        str(IMAGE_BASE),
        "--overlay",
        str(overlay),
        "--require-curated-ids",
        "-o",
        str(out),
        allowlist_env=",".join(CURATED_IDS),
    )
    assert result.returncode != 0, result.stdout
    assert "deepseek/deepseek-v4.1-flash" in result.stderr, result.stderr
    assert not out.exists()


def test_an_empty_allowlist_asserts_nothing(tmp_path):
    """No curated set configured means nothing to assert; the merge still
    succeeds."""
    out = tmp_path / "litellm.runtime.yaml"
    result = _run(
        "--base",
        str(IMAGE_BASE),
        "--overlay",
        str(REPO_OVERLAY),
        "--require-curated-ids",
        "-o",
        str(out),
    )
    assert result.returncode == 0, result.stderr
    assert out.is_file()


def test_a_missing_overlay_file_fails_loudly(tmp_path):
    """A missing overlay asset must be a named error, not a traceback."""
    out = tmp_path / "litellm.runtime.yaml"
    result = _run(
        "--base",
        str(IMAGE_BASE),
        "--overlay",
        str(tmp_path / "no-such-overlay.yaml"),
        "--allowlist",
        ",".join(CURATED_IDS),
        "--require-curated-ids",
        "-o",
        str(out),
    )
    assert result.returncode != 0, result.stdout
    assert "no-such-overlay.yaml" in result.stderr, result.stderr
    assert not out.exists()
