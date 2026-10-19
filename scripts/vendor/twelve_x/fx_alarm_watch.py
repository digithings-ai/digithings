"""Which labelled FX alarm issues hold activity the board has not reported yet.

DIG-54.7. Pure on purpose: the caller fetches the issues and files the Paperclip
report, this only compares. State is keyed by issue_number because one label can
cover many issues, and compared per number because the label itself is permanent and
would otherwise re-file the same alarm on every tick.
"""

from __future__ import annotations

#: The labels the heartbeat and the brief-freshness check raise with. They are the only
#: discriminator between a dead session and a stale brief, because both raise on
#: ``if: failure()``.
ALARM_LABELS = frozenset({"primemarket-session-expired", "fx-briefs-stale"})


def new_alarms(
    issues: list[dict], watermarks: dict[int, str]
) -> tuple[list[int], dict[int, str]]:
    """Return the alarm numbers to report, and the watermarks to persist.

    New means the newest comment moved past the watermark recorded for that number, or
    the number has no watermark at all. With no comment yet the issue's own updated_at
    is the cursor, so an occurrence that arrives as a fresh issue is still reported
    exactly once rather than on every tick.

    Cursors are stored as ``str`` so a value that has been through a JSON round-trip
    still compares equal to the next tick's ``str(cursor)``; GitHub hands back integer
    comment ids, and an int cursor read against a quoted watermark never matches.

    ``watermarks`` must be keyed by int; a JSON document round-trip yields string keys,
    and the caller must restore them or every issue reads as new again.
    """
    reported: list[int] = []
    nxt = dict(watermarks)
    seen: set[int] = set()
    for issue in sorted(issues, key=lambda i: i["number"]):
        if not ALARM_LABELS.intersection(issue["labels"]):
            continue
        number = issue["number"]
        if number in seen:
            continue
        seen.add(number)
        cursor = str(issue["newest_comment_id"] or issue["updated_at"])
        if nxt.get(number) != cursor:
            reported.append(number)
            nxt[number] = cursor
    return reported, nxt
