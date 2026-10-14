#!/usr/bin/env bash
# Smoke: POST a minimal OTLP/HTTP JSON span to self-hosted Langfuse (#4930).
# Fails closed when endpoint or auth headers are missing. Never prints secrets.
set -euo pipefail

ENDPOINT="${DIGITRACE_LANGFUSE_OTLP_ENDPOINT:-${OTEL_EXPORTER_OTLP_ENDPOINT:-}}"
# Prefer Digi header env (#4927), then the OpenTelemetry standard name.
HEADERS_RAW="${DIGI_OTEL_HEADERS:-${OTEL_EXPORTER_OTLP_HEADERS:-}}"

fail() {
  echo "smoke_digitrace_langfuse_otlp: $*" >&2
  exit 1
}

if [[ -z "${ENDPOINT}" ]]; then
  fail "missing DIGITRACE_LANGFUSE_OTLP_ENDPOINT (or OTEL_EXPORTER_OTLP_ENDPOINT). Example: https://trace.digithings.ai/api/public/otel"
fi

if [[ -z "${HEADERS_RAW}" ]]; then
  fail "missing DIGI_OTEL_HEADERS (or OTEL_EXPORTER_OTLP_HEADERS). Expected comma-separated key=value pairs including Authorization=Basic …"
fi

# Normalize endpoint to the Langfuse OTLP traces path when a bare origin is given.
case "${ENDPOINT}" in
  */api/public/otel|*/api/public/otel/)
    OTLP_URL="${ENDPOINT%/}"
    ;;
  */v1/traces)
    OTLP_URL="${ENDPOINT}"
    ;;
  *)
    OTLP_URL="${ENDPOINT%/}/api/public/otel"
    ;;
esac

# Build curl -H args from key=value pairs without echoing values.
CURL_HEADERS=()
AUTH_SEEN=0
IFS=',' read -r -a _pairs <<< "${HEADERS_RAW}"
for pair in "${_pairs[@]}"; do
  pair="${pair#"${pair%%[![:space:]]*}"}"
  pair="${pair%"${pair##*[![:space:]]}"}"
  [[ -z "${pair}" ]] && continue
  key="${pair%%=*}"
  val="${pair#*=}"
  if [[ -z "${key}" || "${key}" == "${pair}" ]]; then
    fail "invalid header pair (expected key=value); refusing to continue"
  fi
  if [[ "${key}" == "Authorization" || "${key}" == "authorization" ]]; then
    AUTH_SEEN=1
  fi
  CURL_HEADERS+=(-H "${key}: ${val}")
done

if [[ "${AUTH_SEEN}" -ne 1 ]]; then
  fail "auth header missing: DIGI_OTEL_HEADERS must include Authorization=Basic …"
fi

# Minimal OTLP/HTTP JSON ExportTraceServiceRequest (one span).
# Timestamp: unix nano as string (OTLP JSON).
NOW_NS="$(python3 -c 'import time; print(str(int(time.time()*1e9)))')"
END_NS="$(python3 -c "print(str(int('${NOW_NS}')+1000000))")"

PAYLOAD="$(python3 - <<PY
import json
now = "${NOW_NS}"
end = "${END_NS}"
doc = {
  "resourceSpans": [{
    "resource": {
      "attributes": [
        {"key": "service.name", "value": {"stringValue": "digitrace-langfuse-smoke"}}
      ]
    },
    "scopeSpans": [{
      "scope": {"name": "digitrace.smoke", "version": "0.1.0"},
      "spans": [{
        "traceId": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "spanId": "bbbbbbbbbbbbbbbb",
        "name": "digitrace.langfuse.otlp.smoke",
        "kind": 1,
        "startTimeUnixNano": now,
        "endTimeUnixNano": end,
        "attributes": [
          {"key": "digitrace.smoke", "value": {"boolValue": True}}
        ],
        "status": {"code": 1}
      }]
    }]
  }]
}
print(json.dumps(doc))
PY
)"

# Do not print headers or payload secrets. Show only HTTP status.
HTTP_CODE="$(
  curl -sS -o /tmp/digitrace-langfuse-otlp-smoke.body -w "%{http_code}" \
    -X POST "${OTLP_URL}" \
    -H "Content-Type: application/json" \
    "${CURL_HEADERS[@]}" \
    --data "${PAYLOAD}" \
    || fail "curl failed talking to OTLP endpoint (host/DNS/TLS). Body not shown."
)"

if [[ "${HTTP_CODE}" != "200" && "${HTTP_CODE}" != "201" && "${HTTP_CODE}" != "202" ]]; then
  # Never dump Authorization. Short generic body hint only.
  body_hint="$(head -c 200 /tmp/digitrace-langfuse-otlp-smoke.body 2>/dev/null | tr '\n' ' ' || true)"
  rm -f /tmp/digitrace-langfuse-otlp-smoke.body
  fail "OTLP export HTTP ${HTTP_CODE} (expected 200/201/202). Body hint (truncated): ${body_hint}"
fi

rm -f /tmp/digitrace-langfuse-otlp-smoke.body
echo "smoke_digitrace_langfuse_otlp: ok (HTTP ${HTTP_CODE})"
