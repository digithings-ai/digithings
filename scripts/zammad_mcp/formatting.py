"""Plain-text formatting for Zammad tickets (no MCP dependency)."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

MAX_ARTICLE_BODY_CHARS = 4000
MAX_ARTICLES_SHOWN = 50

_BLOCK_TAGS = {
    "article",
    "blockquote",
    "br",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tr",
    "ul",
}
_SKIP_TAGS = {"head", "script", "style"}


class _HtmlToText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        lines = []
        for raw_line in "".join(self._parts).splitlines():
            collapsed = re.sub(r"[ \t]+", " ", raw_line).strip()
            if collapsed:
                lines.append(collapsed)
        return "\n".join(lines)


def html_to_text(value: Any) -> str:
    """Convert an HTML article body to readable plain text."""
    raw = "" if value is None else str(value)
    if not raw.strip():
        return ""
    parser = _HtmlToText()
    parser.feed(raw)
    parser.close()
    return parser.text()


def _field(value: Any) -> str:
    """Best-effort string for ids/names; None/empty/'-' → ''."""
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("name", "login", "email", "title", "fullname"):
            candidate = value.get(key)
            if candidate:
                return str(candidate)
        return ""
    text = str(value).strip()
    return "" if text == "-" else text


def _labeled(label: str, value: Any) -> str:
    text = _field(value)
    return f"{label}: {text}" if text else ""


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _mask_customer(value: Any) -> str:
    """Mask a customer email: keep only the first local-part character."""
    raw = value.get("email") if isinstance(value, dict) else value
    text = _field(raw)
    if not _EMAIL_RE.match(text):
        return text
    local, _, domain = text.partition("@")
    return f"{local[0]}***@{domain}"


def format_ticket_line(ticket: dict[str, Any]) -> str:
    """One-line summary used in search results."""
    ticket_id = _field(ticket.get("id")) or "?"
    number = _field(ticket.get("number"))
    state = _field(ticket.get("state")) or "unknown"
    title = _field(ticket.get("title")) or "(no title)"
    head = f"- id {ticket_id}"
    if number:
        head += f" #{number}"
    head += f" [{state}] {title}"
    tail = " | ".join(
        part
        for part in (
            _labeled("group", ticket.get("group")),
            _labeled("priority", ticket.get("priority")),
            _labeled("customer", _mask_customer(ticket.get("customer"))),
            _labeled("owner", ticket.get("owner")),
            _labeled("updated", ticket.get("updated_at")),
        )
        if part
    )
    return f"{head} | {tail}" if tail else head


def format_search_results(
    query: str,
    tickets: list[dict[str, Any]],
    fallback_terms: list[str] | None = None,
) -> str:
    """Render a search response for the model."""
    if not tickets:
        if fallback_terms:
            tried = ", ".join(fallback_terms)
            return f'No tickets matched: "{query}" (also tried keywords: {tried})'
        return f'No tickets matched: "{query}"'
    header = f'Found {len(tickets)} ticket(s) for: "{query}"'
    if fallback_terms:
        header += f" (matched via keywords: {', '.join(fallback_terms)})"
    lines = [header]
    lines.extend(format_ticket_line(ticket) for ticket in tickets)
    return "\n".join(lines)


def format_ticket_list(tickets: list[dict[str, Any]], page: int = 1, per_page: int = 50) -> str:
    """Render one page of the visible ticket list for the model."""
    if not tickets:
        if page > 1:
            return f"No tickets on page {page}; try earlier pages."
        return "No tickets visible to this token."
    lines = [f"Visible tickets (page {page}, {len(tickets)} shown):"]
    lines.extend(format_ticket_line(ticket) for ticket in tickets)
    if len(tickets) == per_page:
        lines.append(f"Page is full; continue with page {page + 1}.")
    lines.append("Read a full conversation with get_ticket(id or #number).")
    return "\n".join(lines)


_EXTRA_FIELDS = (
    ("impact", "impact"),
    ("environment", "environment"),
    ("build", "build_number"),
    ("tenant", "tenant_ref"),
    ("job", "job_ref"),
    ("report", "report_ref"),
    ("escalation", "escalation_at"),
    ("first response", "first_response_at"),
    ("closed", "close_at"),
    ("jira", "jira_key"),
)


def _extras_line(ticket: dict[str, Any]) -> str:
    parts = [
        part for part in (_labeled(label, ticket.get(key)) for label, key in _EXTRA_FIELDS) if part
    ]
    jira_meta = [
        item
        for item in (_field(ticket.get("jira_status")), _field(ticket.get("jira_assignee")))
        if item
    ]
    if jira_meta:
        parts.append(f"jira meta: {', '.join(jira_meta)}")
    return " | ".join(parts)


def _format_article(index: int, article: dict[str, Any]) -> list[str]:
    header_bits = [f"--- article {index}"]
    created = _field(article.get("created_at"))
    if created:
        header_bits.append(f"({created})")
    sender = _field(article.get("sender")) or "unknown"
    kind = _field(article.get("type")) or "unknown"
    header_bits.append(f"{sender}/{kind}")
    if article.get("internal"):
        header_bits.append("[internal]")
    author = _field(article.get("from"))
    if author:
        header_bits.append(f"from {author}")
    lines = [" ".join(header_bits)]
    subject = _field(article.get("subject"))
    if subject:
        lines.append(f"Subject: {subject}")
    body = html_to_text(article.get("body"))
    if body:
        if len(body) > MAX_ARTICLE_BODY_CHARS:
            body = body[:MAX_ARTICLE_BODY_CHARS].rstrip() + "\n... [truncated]"
        lines.append(body)
    return lines


def format_ticket_detail(ticket: dict[str, Any], articles: list[dict[str, Any]]) -> str:
    """Render one ticket with its articles for the model.

    Internal notes are omitted and customer emails are masked — the OCC
    embed is anonymous, so tool output must not leak helpdesk-internal data.
    """
    ticket_id = _field(ticket.get("id")) or "?"
    number = _field(ticket.get("number"))
    title = _field(ticket.get("title")) or "(no title)"
    head = f"Ticket {ticket_id}"
    if number:
        head += f" #{number}"
    lines = [f"{head}: {title}"]
    visible = [article for article in articles if not article.get("internal")]
    hidden = len(articles) - len(visible)
    identity = " | ".join(
        part
        for part in (
            _labeled("State", ticket.get("state")),
            _labeled("Group", ticket.get("group")),
            _labeled("Priority", ticket.get("priority")),
            _labeled("Type", ticket.get("type")),
        )
        if part
    )
    if identity:
        lines.append(identity)
    people = " | ".join(
        part
        for part in (
            _labeled("Customer", _mask_customer(ticket.get("customer"))),
            _labeled("Organization", ticket.get("organization")),
            _labeled("Owner", ticket.get("owner")),
        )
        if part
    )
    if people:
        lines.append(people)
    timeline = " | ".join(
        part
        for part in (
            _labeled("Created", ticket.get("created_at")),
            _labeled("Updated", ticket.get("updated_at")),
            f"Articles: {len(visible)}",
        )
        if part
    )
    lines.append(timeline)
    extras = _extras_line(ticket)
    if extras:
        lines.append(f"Extras: {extras}")
    note = _field(ticket.get("note"))
    if note:
        lines.append(f"Note: {note}")
    lines.append("")
    lines.append(f"Articles ({len(visible)}):")
    for index, article in enumerate(visible[:MAX_ARTICLES_SHOWN], start=1):
        lines.extend(_format_article(index, article))
    remaining = len(visible) - MAX_ARTICLES_SHOWN
    if remaining > 0:
        lines.append(f"... {remaining} more article(s) omitted")
    if hidden > 0:
        lines.append(f"... {hidden} internal note(s) omitted")
    return "\n".join(lines)


CLOSED_STATE_NAMES = {"closed", "merged"}
RECENT_WINDOW_DAYS = 7


def _parse_timestamp(value: Any) -> datetime | None:
    text = _field(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _counts_line(label: str, counter: Counter[str]) -> str:
    ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0].lower()))
    return f"{label}: " + ", ".join(f"{name} {count}" for name, count in ordered)


def format_ticket_report(tickets: list[dict[str, Any]], now: datetime | None = None) -> str:
    """Aggregate visible tickets into a compact status report.

    "Closed" counts states named ``closed``/``merged`` (Zammad's closed-type
    defaults); any other state is reported as unresolved.
    """
    total = len(tickets)
    if total == 0:
        return "Zammad ticket report: no tickets visible to this token."
    states: Counter[str] = Counter(_field(ticket.get("state")) or "unknown" for ticket in tickets)
    closed = sum(count for name, count in states.items() if name.lower() in CLOSED_STATE_NAMES)
    groups: Counter[str] = Counter(_field(ticket.get("group")) or "unknown" for ticket in tickets)
    priorities: Counter[str] = Counter(
        _field(ticket.get("priority")) or "unknown" for ticket in tickets
    )
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=RECENT_WINDOW_DAYS)
    recent = 0
    for ticket in tickets:
        updated = _parse_timestamp(ticket.get("updated_at"))
        if updated is not None and updated >= cutoff:
            recent += 1
    lines = [
        f"Zammad ticket report ({total} ticket(s) visible)",
        f"Unresolved: {total - closed} | Closed: {closed}",
        _counts_line("By state", states),
        _counts_line("By group", groups),
        _counts_line("By priority", priorities),
        f"Updated in the last {RECENT_WINDOW_DAYS} days: {recent}",
    ]
    return "\n".join(lines)
