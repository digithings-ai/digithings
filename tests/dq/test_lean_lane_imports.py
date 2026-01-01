"""Lean-lane import guard: portfolio modules must import without openai.

CI's digiquant lane has no openai (digillm.client imports it at top
level); a top-level digigraph.graph import pulls the whole LLM stack and
breaks collection of every test importing the module (ModuleNotFoundError).
This test simulates the lean lane in a subprocess and fails loudly if the
chain returns.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit

_LEAN_GUARD_CODE = (
    "import sys, importlib.abc\n"
    "class _BlockOpenAI(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'openai' or name.startswith('openai.'):\n"
    "            raise ImportError('blocked lean-lane simulation')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _BlockOpenAI())\n"
    "import digiquant.portfolio.phases.phase7e_risk_sizing\n"
    "import digiquant.portfolio.portfolio_materialize\n"
    "import tests.dq.test_market_data_parity\n"
    "print('lean-lane import ok')\n"
)


def test_portfolio_modules_importable_without_openai() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", _LEAN_GUARD_CODE],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    assert "lean-lane import ok" in proc.stdout
