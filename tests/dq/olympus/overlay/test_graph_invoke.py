"""Overlay graph invoke stamps the pin seam and refuses house (T4).

Does not import ``overlay.byok`` / digillm — the invoke callable is injected.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from digiquant.olympus.overlay.graph_invoke import (
    build_overlay_chain,
    overlay_config_bundle,
)
from digiquant.olympus.overlay.models import OverlayError
from digiquant.olympus.tenancy import house_workspace_id, system_workspace_id

pytestmark = pytest.mark.unit

_RUN = date(2026, 8, 31)


def test_overlay_config_bundle_stamps_workspace_and_version() -> None:
    workspace = uuid4()
    version = uuid4()
    bundle = overlay_config_bundle(
        workspace_id=workspace,
        profile_version_id=version,
        watchlist=("SPY",),
    )
    assert bundle.workspace_id == str(workspace)
    assert bundle.profile_config_version_id == str(version)
    assert bundle.watchlist == ["SPY"]
    assert bundle.workspace_id != str(house_workspace_id())


def test_overlay_config_bundle_refuses_house_and_system() -> None:
    version = uuid4()
    with pytest.raises(OverlayError, match="house"):
        overlay_config_bundle(
            workspace_id=house_workspace_id(),
            profile_version_id=version,
        )
    with pytest.raises(OverlayError, match="house"):
        overlay_config_bundle(
            workspace_id=system_workspace_id(),
            profile_version_id=version,
        )


def test_build_overlay_chain_invokes_with_pin_and_manage_usage_false() -> None:
    workspace = uuid4()
    version = uuid4()
    seen: dict[str, object] = {}

    def invoke(**kwargs: object) -> None:
        seen.update(kwargs)

    chain = build_overlay_chain(
        workspace_id=workspace,
        profile_version_id=version,
        invoke=invoke,
    )
    chain(workspace_id=workspace, run_date=_RUN, requested_version_id=version)
    assert seen["workspace_id"] == workspace
    assert seen["run_date"] == _RUN
    assert seen["requested_version_id"] == version
    assert seen["manage_usage"] is False
