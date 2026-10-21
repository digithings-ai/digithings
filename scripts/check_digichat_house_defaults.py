#!/usr/bin/env python3
"""Fail when house drifts from defaults.yaml or a picker id leaves the catalog.

House is ``apps/digichat/config/defaults.yaml``. The digithings.ai example is an
``extends: defaults`` pointer. OCC and the DataTap trial leave
``gate.showContextMeter`` unset. Model ids on the house surfaces below must be
rows in ``model-picker-catalog.json``. ``config/litellm.yaml`` is exempt
(DIG-4982).

Run from the repo root: python scripts/check_digichat_house_defaults.py
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
DEFAULTS = REPO / "apps/digichat/config/defaults.yaml"
CATALOG = REPO / "apps/digichat/config/model-picker-catalog.json"
EXAMPLE = REPO / "apps/digichat/config/examples/digithings-ai-embed.yaml"
OCC = REPO / "apps/digichat/config/examples/occ-embed.yaml"
DATATAP = REPO / "apps/digichat/config/datatap-trial-foundry.yaml"
DEPLOY = REPO / "apps/digichat/config/digichat-deploy-models.json"
WRANGLER = REPO / "apps/digithings-stack-cloudflare/wrangler.toml"
DIGIPROJECT = REPO / "docs/projects/digithings/digiproject.yaml"
POLICY = REPO / "config/model-policy.json"
CHEAPER = REPO / "config/litellm.cheaperinference.yaml"
LITELLM = REPO / "config/litellm.yaml"

BANNED = (
    "gemini-3.7-flash",
    "deepseek/deepseek-v4-pro",
    "google/gemini-3.7-flash",
    "gpt-4o-mini",
)
HOUSE_HOSTS = [
    "digithings.ai",
    "www.digithings.ai",
    "occ.digithings.ai",
    "digiquant.io",
    "www.digiquant.io",
]
GRAPH_TOOLS = ["digisearch", "digivault_search_notes", "digivault_get_note"]
PROMPT_MARK = "Web search is on."


def fail(problems: list[str]) -> int:
    for problem in problems:
        print(f"FAIL {problem}", file=sys.stderr)
    return 1 if problems else 0


def main() -> int:
    problems: list[str] = []
    defaults = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
    house = defaults["deployment"]
    gate = house["gate"]
    if gate.get("showContextMeter") is not True:
        problems.append("defaults.yaml house gate.showContextMeter must be true")
    if gate.get("webSearch") is not True:
        problems.append("defaults.yaml house gate.webSearch must be true")
    user_tpm = (house.get("guardrails") or {}).get("tokensPerMinute", {}).get("user")
    if user_tpm != 80000:
        problems.append(f"defaults.yaml guardrails.tokensPerMinute.user is {user_tpm}, want 80000")
    guardrails = house.get("guardrails") or {}
    if guardrails.get("maxToolCallsPerTurn") != 5:
        problems.append("defaults.yaml maxToolCallsPerTurn must be 5")
    if guardrails.get("answerAt") != 0.7 or guardrails.get("pauseAt") != 0.9:
        problems.append("defaults.yaml answer guard must be answerAt 0.7 and pauseAt 0.9")
    if (guardrails.get("tokensPerMinute") or {}).get("deployment") is not None:
        problems.append("defaults.yaml must not set a shared deployment TPM")
    if guardrails.get("rateLimit") is not True:
        problems.append("defaults.yaml guardrails.rateLimit must be true")
    prompt = house.get("prompt") or ""
    if PROMPT_MARK not in prompt:
        problems.append("defaults.yaml prompt must say web search is on")
    if defaults.get("embedHosts") != HOUSE_HOSTS:
        problems.append(f"defaults.yaml embedHosts {defaults.get('embedHosts')} != {HOUSE_HOSTS}")
    if defaults.get("graphTools") != GRAPH_TOOLS:
        problems.append("defaults.yaml graphTools drifted from the digiproject tool list")
    if house.get("models", {}).get("default") != "deepseek/deepseek-v4.1-flash-1017":
        problems.append("defaults.yaml default model is not deepseek-v4.1-flash-1017")

    example = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    if example.get("extends") != "defaults" or "hosts" in example or "deployment" in example:
        problems.append("digithings-ai-embed.yaml must be an extends: defaults pointer")

    for label, path in (("occ", OCC), ("datatap", DATATAP)):
        overlay = yaml.safe_load(path.read_text(encoding="utf-8"))
        blob = json.dumps(overlay)
        if '"showContextMeter": true' in blob or "showContextMeter: true" in path.read_text(
            encoding="utf-8"
        ):
            problems.append(f"{label} overlay must not turn showContextMeter on")

    occ = yaml.safe_load(OCC.read_text(encoding="utf-8"))
    occ_guard = ((occ.get("hosts") or {}).get("occ.digithings.ai") or {}).get("guardrails") or {}
    if occ_guard.get("rateLimit") is not False:
        problems.append("occ overlay must set guardrails.rateLimit false")
    if occ_guard.get("tokensPerMinute") is not None:
        problems.append("occ overlay must clear tokensPerMinute")
    for inherited in ("maxToolCallsPerTurn", "answerAt", "pauseAt"):
        if inherited in occ_guard:
            problems.append(f"occ overlay must inherit {inherited} from defaults")

    trial_text = DATATAP.read_text(encoding="utf-8")
    if "TODO" not in trial_text:
        problems.append("datatap trial must leave the shared TPM as a TODO")
    trial = yaml.safe_load(trial_text)
    trial_guard = ((trial.get("deployment") or {}).get("guardrails") or {})
    if trial_guard.get("tokensPerMinute") is not None:
        problems.append("datatap trial must leave tokensPerMinute unset")
    if "rateLimit" in trial_guard:
        problems.append("datatap trial must inherit the request limiter")

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    catalog_ids = {row["id"] for row in catalog["models"]}
    for banned in ("deepseek/deepseek-v4-pro", "google/gemini-3.7-flash"):
        if banned in catalog_ids:
            problems.append(f"picker catalog still contains {banned}")

    deploy = json.loads(DEPLOY.read_text(encoding="utf-8"))
    for key in ("default",):
        if deploy[key] not in catalog_ids:
            problems.append(f"deploy models {key} {deploy[key]} is not in the catalog")
    for id_ in [*deploy["available"], *deploy["sessionAllowlist"]]:
        if id_ not in catalog_ids:
            problems.append(f"deploy model {id_} is not in the catalog")

    wrangler = tomllib.loads(WRANGLER.read_text(encoding="utf-8"))
    allow = wrangler["vars"]["DIGI_SESSION_MODEL_ALLOWLIST"].split(",")
    if allow != deploy["sessionAllowlist"]:
        problems.append("wrangler DIGI_SESSION_MODEL_ALLOWLIST drifted from digichat-deploy-models.json")

    project = yaml.safe_load(DIGIPROJECT.read_text(encoding="utf-8"))
    project_prompt = project["agents"]["research_system_prompt"]
    if " ".join(project_prompt.split()) != " ".join(prompt.split()):
        problems.append("digiproject research_system_prompt drifted from defaults.yaml prompt")
    if project["agents"]["allowed_tools"] != GRAPH_TOOLS:
        problems.append("digiproject allowed_tools drifted from defaults.yaml graphTools")

    corpus = json.loads(wrangler["vars"]["DIGI_TENANT_CORPUS_MAP"])
    corpus_prompt = corpus["digithings"].get("researchSystemPrompt", "")
    if " ".join(corpus_prompt.split()) != " ".join(prompt.split()):
        problems.append("wrangler digithings prompt drifted from defaults.yaml")

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    if policy.get("fallback_model") != "deepseek/deepseek-v4.1-flash-1017":
        problems.append("model-policy fallback_model is not the 1017 house default")

    scanned = {
        DEFAULTS: DEFAULTS.read_text(encoding="utf-8"),
        EXAMPLE: EXAMPLE.read_text(encoding="utf-8"),
        DEPLOY: DEPLOY.read_text(encoding="utf-8"),
        CHEAPER: CHEAPER.read_text(encoding="utf-8"),
        POLICY: POLICY.read_text(encoding="utf-8"),
    }
    for path, text in scanned.items():
        for banned in BANNED:
            if banned in text and path != LITELLM:
                # deepseek-v4-pro-0813 contains the banned prefix deepseek/deepseek-v4-pro
                if banned == "deepseek/deepseek-v4-pro" and "deepseek/deepseek-v4-pro-0813" in text:
                    stripped = text.replace("deepseek/deepseek-v4-pro-0813", "")
                    if banned not in stripped:
                        continue
                problems.append(f"{path.relative_to(REPO)} still names {banned}")

    return fail(problems)


if __name__ == "__main__":
    sys.exit(main())
