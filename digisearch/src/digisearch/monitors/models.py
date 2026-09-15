"""Phase C monitor models — the canonical Watch / MonitorRun envelope (#4065).

Monitors are scheduled web searches with dedup and delivery. This module is the
model layer only; Tasks 2–8 (store, dedup, runner, delivery, HTTP, MCP, EXA
adapter) build on these shapes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from digisearch.web_exa import VALID_SEARCH_TYPES


class WatchSchedule(BaseModel):
    """When a watch runs.

    ``cron`` uses the same 5-field grammar as ``digiclaw/cron.py`` (grammar
    validation happens at the runner seam, not here). ``interval_seconds``
    mirrors digiclaw's continuous sleep; the ``ge=60`` floor is deliberately
    stricter than digiclaw's own ``ge=1``.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["cron", "interval"]
    cron: str | None = None
    interval_seconds: int | None = Field(default=None, ge=60)
    enabled: bool = True
    timezone: str = "UTC"

    @model_validator(mode="after")
    def _require_mode_field(self) -> WatchSchedule:
        if self.mode == "cron" and not self.cron:
            raise ValueError("cron is required when mode=cron")
        if self.mode == "interval" and self.interval_seconds is None:
            raise ValueError("interval_seconds is required when mode=interval")
        return self


class DedupRule(BaseModel):
    """How a run decides which results are new (Task 3)."""

    model_config = ConfigDict(extra="forbid")

    match: Literal["url", "url_content"] = "url_content"
    similarity_threshold: float = Field(default=0.9, ge=0.0, le=1.0)


class DeliveryTarget(BaseModel):
    """One delivery destination. ``url`` is webhook/slack; ``email_to`` email."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["webhook", "slack", "email"]
    url: str | None = None
    email_to: list[str] | None = None


class DeliveryConfig(BaseModel):
    """Delivery mode and destinations. ``poll`` (the default) stores runs only."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["poll", "webhook", "fanout"] = "poll"
    targets: list[DeliveryTarget] = Field(default_factory=list, max_length=5)


class Watch(BaseModel):
    """A scheduled web-search watch.

    Backend notes:

    - ``search_type`` and ``category`` are EXA-only: they are ignored on the
      OSS path (``WebSearchRequest`` has no such fields).
    - ``num_results`` is the EXA 1-100 cap (R6). The OSS seam clamps to
      ``min(num_results, 10)`` and records ``num_results_clamped_from`` in the
      run's ``query_snapshot``; this model keeps the EXA bound so one shape
      spans both backends.
    - Monitors pin ``recency_days=None`` at the runner seam (R5): no rolling
      window is baked into this model, so the landed ``WebSearchRequest``
      default of 7 days is never silently inherited.
    - There is deliberately no ``delivery_secret`` field (R8): the secret is
      generated server-side and returned only in create/rotate responses.
    - ``exa_monitor_id`` identifies the remote EXA monitor and is required
      once ``backend="exa"`` (enforced by the Task 8 create path).
    """

    model_config = ConfigDict(extra="forbid")

    watch_id: str = ""
    name: str = Field(min_length=1, max_length=120)
    query: str = Field(min_length=1, max_length=500)
    search_type: str = "auto"
    num_results: int = Field(default=8, ge=1, le=100)
    category: str | None = None
    include_domains: list[str] = Field(default_factory=list, max_length=5)
    exclude_domains: list[str] = Field(default_factory=list, max_length=20)
    schedule: WatchSchedule
    dedup: DedupRule = Field(default_factory=DedupRule)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    backend: Literal["oss", "exa"] = "oss"
    exa_monitor_id: str | None = None
    workspace_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("search_type")
    @classmethod
    def _validate_search_type(cls, value: str) -> str:
        if value not in VALID_SEARCH_TYPES:
            raise ValueError(f"invalid search_type: {value!r}")
        return value


class DeliveryReceipt(BaseModel):
    """Outcome of one delivery attempt (Task 5)."""

    target_kind: str
    ok: bool
    status_code: int | None = None
    error: str | None = None


class MonitorRun(BaseModel):
    """Canonical run envelope — backend is a label, never a shape fork.

    OSS runs are born in this shape; EXA runs are translated into it by
    ``exa_adapter`` (Task 8). Status semantics: ``ok`` = new content found and
    stored/delivered; ``no_change`` = turn succeeded but dedup removed
    everything (delivery skipped, run still persisted); ``failed`` = the turn
    raised or the backend errored (``error`` set, delivery skipped).
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    watch_id: str
    backend: Literal["oss", "exa"] = "oss"
    status: Literal["ok", "no_change", "failed"]
    trigger: Literal["schedule", "manual", "poll", "exa_webhook"]
    started_at: datetime
    finished_at: datetime
    query_snapshot: dict[str, Any]
    results_all: list[dict[str, Any]]
    results_new: list[dict[str, Any]]
    dedup_stats: dict[str, int]
    cost_dollars: dict[str, Any] | None = None
    delivery: list[DeliveryReceipt] = Field(default_factory=list)
    error: str | None = None
