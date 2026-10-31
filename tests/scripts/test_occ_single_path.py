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
    # The second argument is the (trimmed) invite key, whatever its local name.
    assert re.search(r"containerUpstream\(occContainerRequest\(request, \w+\)\)", src), (
        "the valid branch must send a rewritten container request, never the original request"
    )
    assert "containerUpstream(request)" not in src, (
        "the gate is self-fetching the original request again"
    )


def test_the_invite_link_does_not_leave_the_key_in_the_address_bar() -> None:
    """DIG-1437: the key must not sit in the URL after the first load.

    The Pages shell used to strip it client-side (`stripInviteTokenFromUrl` +
    `replaceState`). After the consolidation the edge owns that: the token arm
    answers a 302 to the tokenless URL and sets the cookie, so the browser
    re-requests with the cookie and the key is out of the location bar and
    history without needing JavaScript.
    """
    src = _read(WORKER / "occ-gate.ts")
    assert re.search(r"status:\s*302", src), (
        "the invite arm must redirect; returning 200 leaves ?token= in the address bar"
    )
    assert re.search(r"location:\s*clean\.toString\(\)", src), (
        "the redirect must target the same URL with `token` removed"
    )
    assert re.search(r'clean\.searchParams\.delete\("token"\)', src), (
        "the redirect target still carries the invite key"
    )


def test_the_container_route_and_header_the_gate_targets_are_real() -> None:
    """The seam has two halves, and this pins the app's half.

    A rename of the app's embed route, or a change of the header it reads, would
    leave every Worker test green while `/chat/occ` 404s in production — the
    same wiring-gap class this change exists to close.
    """
    route = REPO / "apps" / "digichat" / "src" / "app" / "(digichat)" / "embed" / "page.tsx"
    assert route.is_file(), f"the gate rewrites to a route that does not exist: {route}"

    app_src = REPO / "apps" / "digichat" / "src"
    consumers = [
        path
        for path in app_src.rglob("*")
        if path.suffix in {".ts", ".tsx"} and "x-embed-token" in path.read_text(encoding="utf-8")
    ]
    assert consumers, (
        "nothing in the app reads x-embed-token: the edge would set a header the "
        "container ignores, and the invite would never authenticate a turn"
    )
