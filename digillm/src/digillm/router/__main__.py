"""Read one JSON request on stdin and write one decision on stdout.

The process does not call a model. A bad request exits 2 with
``{"error":"invalid_request"}`` and does not echo the question.
"""

from __future__ import annotations

import json
import sys

from pydantic import ValidationError

from digillm.router.decide import route_query
from digillm.router.types import RouterError, RouterRequest


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
        request = RouterRequest.model_validate(payload)
        decision = route_query(
            text=request.text,
            allowed=list(request.allowed),
            fallback=request.fallback,
            routes=request.routes,
        )
    except (json.JSONDecodeError, ValidationError, RouterError):
        sys.stdout.write(json.dumps({"error": "invalid_request"}) + "\n")
        return 2
    sys.stdout.write(decision.model_dump_json() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
