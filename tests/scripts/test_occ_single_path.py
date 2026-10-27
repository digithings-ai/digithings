"""OCC is one path, one gate, one secret (2026-10-27 consolidation).

The regression this pins is not a unit-level behaviour, it is a *wiring* one:
`occGate(request, key)` used to fall back to `fetch(request)` — a fetch of the
URL the Worker was already serving — and every unit test injected a stub
upstream, so the suite stayed green while the production path was never the one
under test. The same shape had two gates and two copies of the same secret
(Worker + Pages), and the Pages copy could drift from the Worker's without any
test noticing.

So this file asserts the wiring, not the gate logic:

* the Worker passes a real container upstream to `occGate` (the third argument),
* the gate rewrites `/chat/occ` onto the app's own embed route,
* the invite moves out of the URL into `x-embed-token`,
* the Pages shell and its Pages twin gate no longer exist.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKER = REPO / "apps" / "digichat-cloudflare" / "src"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def test_the_worker_hands_the_gate_a_container_upstream() -> None:
    """`occGate` must not be called with only the request and the key.

    That is exactly the old call, and its default upstream was `fetch` — a
    subrequest to the Worker's own URL. The third argument is what makes the
    valid-invite path reach the container.
    """
    src = _read(WORKER / "index.ts")
    call = re.search(r"occGate\(([^;]*?)\);", src, re.DOTALL)
    assert call, "index.ts no longer calls occGate"
    args = [a.strip() for a in call.group(1).split(",")]
    assert len(args) >= 3, (
        "occGate is called with fewer than three arguments — the container "
        f"upstream is missing: {call.group(0)[:160]}"
    )
    assert "container" in call.group(1), (
        "the third argument to occGate must be the container fetch, not the "
        f"default self-fetch: {call.group(0)[:160]}"
    )


def test_the_gate_rewrites_onto_the_app_embed_route() -> None:
    src = _read(WORKER / "occ-gate.ts")

    assert "occContainerRequest" in src, "the gate no longer builds a container request"
    assert re.search(r"pathname\s*=\s*OCC_CONTAINER_PATH", src), (
        "the gate must rewrite the path to the app's embed route"
    )
    assert re.search(r'searchParams\.set\("host",\s*OCC_EMBED_HOST\)', src), (
        "the gate must set the OCC tenant host on the container request"
    )
    assert re.search(r'searchParams\.delete\("token"\)', src), (
        "the invite token must not reach the container URL"
    )
    assert re.search(r"headers\.set\(EMBED_TOKEN_HEADER,\s*invite\)", src), (
        "the invite must travel as x-embed-token, the app's existing transport"
    )


def test_the_pages_shell_and_its_twin_gate_are_gone() -> None:
    """One gate, one secret: a Pages copy would reintroduce the drift."""
    shell = REPO / "apps" / "digithings-web" / "app" / "chat" / "occ" / "page.tsx"
    twin = REPO / "apps" / "digithings-web" / "functions" / "chat" / "occ"
    assert not shell.exists(), f"{shell} still exists — OCC is a Pages shell again"
    assert not twin.exists(), f"{twin} still exists — the Pages twin gate is back"


def test_the_gate_has_no_self_fetch_default() -> None:
    """The old default upstream was `fetch`, which is the bug this pins out.

    A future refactor may keep a default for tests, but the *Worker* must never
    rely on it: that is what `test_the_worker_hands_the_gate_a_container_upstream`
    covers. Here we only refuse the exact old shape — a valid branch that calls
    the upstream with the original request object.
    """
    src = _read(WORKER / "occ-gate.ts")
    assert "containerUpstream(occContainerRequest(request, expected))" in src, (
        "the valid branch must send a rewritten container request, never the original request"
    )
    assert "containerUpstream(request)" not in src, (
        "the gate is self-fetching the original request again"
    )
