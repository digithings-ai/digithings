"""Download route for the ticket exports written by :mod:`scripts.zammad_mcp.exports`.

Runs on the container's :8771 using nothing but the standard library.  ``mcp`` is
deliberately NOT imported here: an mcp upgrade can then never take the download
route down with it, and the handler is testable on a host where mcp is not
installed at all.

The Cloudflare Worker proxies ``/_stack/mcp/zammad-export/<id>`` to this port
through the same fail-closed ``x-digi-mcp-key`` check it applies to the tools,
so this process needs no credential of its own -- it is unreachable except
through that gate, and it is bound to loopback by default.  The Worker forces a
trailing slash on the forwarded path, so ``/<id>``, ``/<id>/`` and
``/<id>.csv`` all have to work.
"""

from __future__ import annotations

import argparse
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from scripts.zammad_mcp.exports import (
    EXPORT_FORMATS,
    ExportError,
    ExportExpired,
    ExportNotFound,
    load_export,
    purge_expired,
    spool_dir,
)

logger = logging.getLogger(__name__)

CONTENT_TYPES = {"json": "application/json; charset=utf-8", "csv": "text/csv; charset=utf-8"}

META_SUFFIX = ".meta.json"


def parse_download_path(path: str) -> tuple[str, str] | None:
    """Map a request path to ``(export_id, format)``, or None when it is not one.

    Accepts ``/<id>``, ``/<id>/`` (the Worker's forced slash), ``/<id>.json`` and
    ``/<id>.csv``.  The id is validated by :func:`load_export`, whose hex-only
    alphabet is what keeps a hostile id from escaping the spool directory.
    """
    raw = unquote(urlsplit(path).path or "/")
    segments = [segment for segment in raw.split("/") if segment]
    if len(segments) != 1:
        return None
    segment = segments[0]
    if segment.endswith(META_SUFFIX):
        return None
    export_id, _, suffix = segment.rpartition(".")
    if not export_id:
        export_id, suffix = segment, ""
    fmt = suffix or "json"
    if fmt not in EXPORT_FORMATS:
        return None
    return export_id, fmt


class ExportRequestHandler(BaseHTTPRequestHandler):
    """Serve one export, or say why not.  No path reaches the filesystem unchecked."""

    server_version = "zammad-export/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self._respond(include_body=True)

    def do_HEAD(self) -> None:
        self._respond(include_body=False)

    def _reject_method(self) -> None:
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED, "only GET and HEAD are supported")

    do_POST = _reject_method
    do_PUT = _reject_method
    do_PATCH = _reject_method
    do_DELETE = _reject_method

    def _respond(self, *, include_body: bool) -> None:
        parsed = parse_download_path(self.path)
        if parsed is None:
            self.send_error(HTTPStatus.NOT_FOUND, "not a ticket export download")
            return
        export_id, fmt = parsed
        try:
            payload, manifest = load_export(export_id, fmt, directory=self._spool())
        except ExportExpired:
            self.send_error(HTTPStatus.GONE, "this export has expired; request a fresh one")
            return
        except ExportNotFound:
            self.send_error(HTTPStatus.NOT_FOUND, "no such ticket export")
            return
        except ExportError as exc:  # defensive: never leak an internal message
            logger.warning("export read failed for %s: %s", export_id, exc)
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "export unreadable")
            return
        self._send(payload, fmt, export_id, include_body=include_body, manifest=manifest)

    def _send(
        self,
        payload: bytes,
        fmt: str,
        export_id: str,
        *,
        include_body: bool,
        manifest: dict[str, Any] | None = None,
    ) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", CONTENT_TYPES[fmt])
        self.send_header("Content-Length", str(len(payload)))
        self.send_header(
            "Content-Disposition", f'attachment; filename="zammad-tickets-{export_id}.{fmt}"'
        )
        self.send_header("Cache-Control", "no-store, private")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        if manifest and manifest.get("expires_at"):
            self.send_header("X-Export-Expires-At", str(manifest["expires_at"]))
        self.end_headers()
        if include_body:
            self.wfile.write(payload)

    def _spool(self):
        override = getattr(self.server, "spool", None)
        return override if override is not None else spool_dir()

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)


def build_server(host: str, port: int, *, spool=None) -> ThreadingHTTPServer:
    """Build the server without starting it (tests bind it directly)."""
    server = ThreadingHTTPServer((host, port), ExportRequestHandler)
    server.spool = spool  # type: ignore[attr-defined]
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve expiring ticket exports (read-only).")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default loopback)")
    parser.add_argument("--port", type=int, default=8771, help="listen port (default 8771)")
    parser.add_argument("--spool", default=None, help="override the export spool directory")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    spool = Path(args.spool) if args.spool else None
    logger.info("purged %s expired export(s) at startup", purge_expired(directory=spool))

    server = build_server(args.host, args.port, spool=spool)
    logger.info("ticket export download route listening on %s:%s", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
