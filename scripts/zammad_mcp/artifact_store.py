"""Writing an oversized Zammad result into the DigiChat artifact store.

This is the transport that replaces the container spool.  The shape is a plain
HTTP POST to the digichat ingest route, using stdlib only - the same constraint
``export_server`` worked under, so this container keeps no framework dependency
and, more importantly, keeps **no storage credential**.

What this container is given
----------------------------
``DIGICHAT_ARTIFACT_INGEST_URL``  where to POST
``DIGICHAT_ARTIFACT_CONVERSATION``  the conversation the artifact belongs to
``DIGICHAT_ARTIFACT_GRANT``        a single-use ingest grant for that conversation

None of those is an object-store or database credential.  The grant names one
conversation and authorises one write into it; the store re-checks that the
caller owns the conversation before it accepts anything, so a leaked grant buys
nothing outside the session it was minted for.  This container therefore never
holds a storage credential, before or after this change.

There is no TTL anywhere in this module.  The artifact's lifetime is the
conversation's: the row is removed by ``ON DELETE CASCADE`` when the
conversation goes, and the link stops validating when the session stops.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from scripts.zammad_mcp.exports import (
    EXPORT_ROW_LIMIT,
    ExportError,
    build_artifact,
    render_metadata_only,
)

_log = logging.getLogger(__name__)


#: Failures that mean "could not store it", never "could not build it".  Both
#: leave the caller free to fall back to the full render, so a row is never lost
#: because the store was unreachable.
class ArtifactStoreError(ExportError):
    """The store could not be reached or refused the write."""


def ingest_url() -> str:
    """Where to POST an artifact, or '' when this container has no route."""
    return (os.environ.get("DIGICHAT_ARTIFACT_INGEST_URL") or "").strip()


def conversation_id() -> str:
    """The conversation the artifact must belong to, or '' when unset."""
    return (os.environ.get("DIGICHAT_ARTIFACT_CONVERSATION") or "").strip()


def ingest_grant() -> str:
    """The single-use grant for this conversation, or '' when unset."""
    return (os.environ.get("DIGICHAT_ARTIFACT_GRANT") or "").strip()


def _ingest(
    artifact: dict[str, Any],
    *,
    tool: str,
    query: str,
    timeout: float,
) -> str:
    url = ingest_url()
    conversation = conversation_id()
    grant = ingest_grant()
    missing = [
        name
        for name, value in (
            ("DIGICHAT_ARTIFACT_INGEST_URL", url),
            ("DIGICHAT_ARTIFACT_CONVERSATION", conversation),
            ("DIGICHAT_ARTIFACT_GRANT", grant),
        )
        if not value
    ]
    if missing:
        raise ArtifactStoreError(
            "artifact ingest is not configured: " + ", ".join(missing) + " unset"
        )

    payload = {
        "conversationId": conversation,
        "token": artifact["token"],
        "name": artifact["name"],
        "mediaType": artifact["mediaType"],
        "kind": artifact["kind"],
        "summary": json.dumps(artifact["summary"], sort_keys=True, default=str),
        "bytes": list(artifact["bytes"]),
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {grant}",
            "X-Conversation-Id": conversation,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        # Deliberately does not echo the response body: the store answers an
        # ownership failure with its own text, and this string can reach a log.
        raise ArtifactStoreError(f"artifact store refused the write: HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ArtifactStoreError(f"artifact store is unreachable: {exc}") from exc

    link = str(body.get("link") or "").strip()
    if not link:
        raise ArtifactStoreError("artifact store accepted the write but returned no link")
    artifact["link"] = link
    return link


def export_if_large(
    tickets: list[dict[str, Any]],
    *,
    tool: str,
    query: str = "",
    preview: list[str] | None = None,
    timeout: float = 5.0,
) -> str | None:
    """The metadata-only render for a large result set, or None below the limit.

    ``preview`` is the already-formatted sample the caller wants shown; it is
    passed in rather than computed here so the caller formats rows with its own
    ``format_ticket_line`` and the two never disagree about what a row looks
    like.

    None means "render the rows the normal way".  It is also what a store failure
    returns: the rows are still in memory and the caller must not lose them.
    """
    if len(tickets or []) <= EXPORT_ROW_LIMIT:
        return None
    try:
        artifact = build_artifact(tickets, tool=tool, query=query)
        link = _ingest(artifact, tool=tool, query=query, timeout=timeout)
    except ExportError as exc:
        _log.warning("artifact store unavailable: %s", exc)
        return None
    return render_metadata_only(artifact, link=link, sample=list(preview or []))
