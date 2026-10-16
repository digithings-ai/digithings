"""Phase D websets provider shims (#4066).

Only :mod:`digisearch.websets.providers.exa_websets` lands in v1: the dormant
EXA Websets Pro translation. The OSS path never imports it — the HTTP/MCP
surfaces keep answering from the OSS store (``backend="oss"``); this package is
the deliberately separate paid alternative.
"""
