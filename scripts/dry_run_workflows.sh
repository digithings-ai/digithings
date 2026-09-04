#!/usr/bin/env bash
# Local replay notes for scheduled / fragile workflows (REM-134).
# Does not invoke GitHub Actions — documents the same checks CI runs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== REM-006/007: enforce-project + project-fields (bash guards) =="
if [[ -f tests/scripts/test_protected_path_bash_guard.sh ]]; then
  bash tests/scripts/test_protected_path_bash_guard.sh
else
  echo "skip: tests/scripts/test_protected_path_bash_guard.sh missing"
fi

echo "== pre-push hook (#2468 deletion taxonomy + #2483 live-trading co-sign) =="
if [[ -f tests/scripts/test_pre_push_hook.sh ]]; then
  bash tests/scripts/test_pre_push_hook.sh
else
  echo "skip: tests/scripts/test_pre_push_hook.sh missing"
fi

echo "== pre-push taxonomy: release-please refs (#2557) =="
if [[ -f tests/scripts/test_branch_taxonomy_release_please.sh ]]; then
  bash tests/scripts/test_branch_taxonomy_release_please.sh
else
  echo "skip: tests/scripts/test_branch_taxonomy_release_please.sh missing"
fi

echo "== install-hooks fail-closed / worktree-safe (#2502) =="
if [[ -f tests/scripts/test_install_hooks.sh ]]; then
  bash tests/scripts/test_install_hooks.sh
else
  echo "skip: tests/scripts/test_install_hooks.sh missing"
fi

echo "== worktree conflict advisory: nested layout + pipefail drain (#2485/#2569) =="
if [[ -f tests/scripts/test_check_worktree_conflicts.sh ]]; then
  bash tests/scripts/test_check_worktree_conflicts.sh
else
  echo "skip: tests/scripts/test_check_worktree_conflicts.sh missing"
fi

echo "== project-stub-fields pause + infer_row (#2566/#2476) =="
python3 -m pytest \
  tests/scripts/test_project_stub_fields_pause.py \
  tests/scripts/test_infer_project_fields_row.py \
  -m unit -q --tb=line

echo "== REM-008: provider-review unit tests (no Claude) =="
python3 -m pytest tests/provider_review/ -m unit -q --tb=line

echo "== REM-009: research compute-technicals (Polars) =="
if [[ -f digiquant/scripts/research/compute-technicals.py ]]; then
  python3 digiquant/scripts/research/compute-technicals.py --help >/dev/null 2>&1 || true
  echo "  (run with real data paths per digiquant/scripts/research/README if needed)"
fi

echo "== REM-095: validate_model_routing =="
python3 scripts/validate_model_routing.py --routing

echo "== REM-128: stack smoke (requires Docker) =="
if command -v docker >/dev/null 2>&1; then
  cp -n .env.example .env 2>/dev/null || cp .env.example .env
  docker compose up -d --wait digikey digigraph digiquant digisearch digismith
  for port in 8005 8000 8001 8002 8003; do
    curl -sf "http://127.0.0.1:${port}/healthz" >/dev/null && echo "  OK :${port}/healthz"
  done
else
  echo "  skip: docker not installed"
fi

echo "Done. See docs/agents/CI_CONVENTIONS.md and docs/reviews/POST-MERGE-AUDIT-RUNBOOK.md"
