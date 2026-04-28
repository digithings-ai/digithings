"""Hermes sub-graph state.

Right now ``HermesState`` is a re-export alias for
:class:`digiquant.atlas.state.AtlasResearchState`. The four moved Hermes
phases (7c / 7cd / 7d / 9) read from raw research-side state slots
(``phase1_outputs``, ``phase2_outputs``, ``phase5_outputs``, etc.), not
just the synthesised digest, so a clean digest-only contract is not yet
viable without a substantial refactor of phase 7c's input shaping.

Why an alias rather than a copy or reimport
-------------------------------------------
The phases type-hint ``HermesState`` rather than ``AtlasResearchState``
deliberately. When the state extraction lands (planned follow-up to
[ADR-0015](../../../../docs/adr/0015-atlas-vs-hermes.md), tracked as a
future ticket on epic #471), the alias here will be replaced with a
proper :class:`pydantic.BaseModel` whose surface is the digest plus
Hermes-private slots. Phase code does not change — only this module does.

Relationship to ADR-0015
------------------------
ADR-0015 names :class:`digiquant.atlas.snapshot.DigestPayload` as the
"only symbol Hermes imports from Atlas." The pragmatic reality on the
2026-04 split is that the analyst / debate / PM phases also touch raw
phase-output slots. The ADR's spirit is preserved — Atlas runtime never
calls into Hermes — but the import surface is wider than the ADR
implies. Tightening to digest-only is a separate refactor.
"""

from __future__ import annotations

from digiquant.atlas.state import AtlasResearchState

# Alias — see module docstring. New code should import ``HermesState`` from
# here so the eventual split lands without churning every phase file.
HermesState = AtlasResearchState

__all__ = ["HermesState"]
