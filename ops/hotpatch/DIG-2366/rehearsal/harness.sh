#!/bin/bash
# DIG-2366 rehearsal harness — measures the two write faults over HTTP.
#
# usage: harness.sh <label> <base_url> <cookiejar> <company_id>
#
# Emits `key=value` measurement lines on stdout. It asserts nothing: judgement is
# left to compare.sh so that a measurement can never be quietly re-labelled as a
# pass. Run it against the unpatched baseline and against the patched bundle and
# diff the two transcripts.

set -uo pipefail

LABEL="$1"
BASE="$2"
COOKIE="$3"
COMPANY="$4"

ORIGIN="Origin: ${BASE}"
FETCH='Sec-Fetch-Site: same-origin'
CT='Content-Type: application/json'
UNKNOWN_UUID='11111111-2222-4333-8444-555555555555'

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

kv() { printf '%s=%s\n' "$1" "$2"; }

# api <method> <path> <body|-> -> prints "HTTP <code>" then the body
api() {
  local method="$1" path="$2" body="$3"
  if [ "$body" = "-" ]; then
    curl -s -m 30 -b "$COOKIE" -H "$ORIGIN" -H "$FETCH" \
      -X "$method" "${BASE}${path}" -o "$WORK/body" -w 'HTTP %{http_code}'
  else
    curl -s -m 30 -b "$COOKIE" -H "$ORIGIN" -H "$FETCH" -H "$CT" \
      -X "$method" "${BASE}${path}" -d "$body" -o "$WORK/body" -w 'HTTP %{http_code}'
  fi
}

jget() { python3 -c "import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: print(''); raise SystemExit
v=d
for k in sys.argv[2].split('.'):
    if isinstance(v,list): v=v[int(k)]
    else: v=v.get(k) if isinstance(v,dict) else None
    if v is None: break
print('' if v is None else v)" "$1" "$2" 2>/dev/null; }

count_docs() { python3 -c "import json,sys
d=json.load(open(sys.argv[1])); print(len(d) if isinstance(d,list) else -1)" "$1" 2>/dev/null; }

kv label "$LABEL"
kv base_url "$BASE"
kv when_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---------------------------------------------------------------- fixture issue
R=$(api POST "/companies/${COMPANY}/issues" '{"title":"DIG-2366 rehearsal probe","description":"rehearsal only"}')
kv create_issue_status "${R##* }"
cp "$WORK/body" "$WORK/issue"
ISSUE=$(jget "$WORK/issue" id)
kv issue_id "$ISSUE"
[ -z "$ISSUE" ] && { kv fatal "issue creation failed"; cat "$WORK/issue"; exit 1; }

# ------------------------------------------------- Fault 1: PUT addressed by a
# document id must not create a second row.
R=$(api PUT "/issues/${ISSUE}/documents/spec" '{"format":"markdown","title":"Spec","body":"# spec\ninitial\n"}')
kv f1_seed_status "${R##* }"
cp "$WORK/body" "$WORK/seed"
DOC_ID=$(jget "$WORK/seed" id)
SEED_REV=$(jget "$WORK/seed" latestRevisionId)
kv f1_seed_doc_id "$DOC_ID"
kv f1_seed_revision_id "$SEED_REV"

api GET "/issues/${ISSUE}/documents" - >/dev/null; cp "$WORK/body" "$WORK/list1"
kv f1_rows_after_seed "$(count_docs "$WORK/list1")"

# read by the document id itself — must resolve to the same document
R=$(api GET "/issues/${ISSUE}/documents/${DOC_ID}" -)
kv f1_get_by_doc_id_status "${R##* }"
cp "$WORK/body" "$WORK/getdocid"
kv f1_get_by_doc_id_resolves_to "$DOC_ID"
[ "$(jget "$WORK/getdocid" id)" = "$DOC_ID" ] && kv f1_get_by_doc_id_same "yes" || kv f1_get_by_doc_id_same "no"

# Probe 1 — write by the document id, no baseRevisionId. This is the reported
# failure mode: the key matches no row, so the unpatched bundle creates a second
# document keyed by the uuid and answers 201.
R=$(api PUT "/issues/${ISSUE}/documents/${DOC_ID}" '{"format":"markdown","body":"# spec\nwritten by document id\n"}')
kv f1_bare_write_status "${R##* }"
cp "$WORK/body" "$WORK/bare"
kv f1_bare_write_key "$(jget "$WORK/bare" key)"
kv f1_bare_write_doc_id "$(jget "$WORK/bare" id)"
kv f1_bare_write_error "$(jget "$WORK/bare" error)"

api GET "/issues/${ISSUE}/documents" - >/dev/null; cp "$WORK/body" "$WORK/list2"
kv f1_rows_after_bare_write "$(count_docs "$WORK/list2")"
kv f1_bare_second_row "$([ "$(count_docs "$WORK/list2")" -gt "$(count_docs "$WORK/list1")" ] && echo yes || echo no)"

# Probe 2 — the same write carrying baseRevisionId, which is what the runbook
# tells callers to send. The unpatched bundle still cannot match the row, so it
# answers 409 "Document does not exist yet"; the patched bundle resolves the key
# and updates the original document.
api GET "/issues/${ISSUE}/documents/spec" - >/dev/null; cp "$WORK/body" "$WORK/spec1"
SPEC_REV="$(jget "$WORK/spec1" latestRevisionId)"
R=$(api PUT "/issues/${ISSUE}/documents/${DOC_ID}" "{\"format\":\"markdown\",\"body\":\"# spec\nwritten by document id with baseRevisionId\n\",\"baseRevisionId\":\"${SPEC_REV}\"}")
kv f1_rebased_write_status "${R##* }"
cp "$WORK/body" "$WORK/rebased"
kv f1_rebased_write_key "$(jget "$WORK/rebased" key)"
kv f1_rebased_write_doc_id "$(jget "$WORK/rebased" id)"
kv f1_rebased_write_error "$(jget "$WORK/rebased" error)"

api GET "/issues/${ISSUE}/documents" - >/dev/null; cp "$WORK/body" "$WORK/list4"
kv f1_rows_after_rebased_write "$(count_docs "$WORK/list4")"
kv f1_rebased_second_row "$([ "$(count_docs "$WORK/list4")" -gt "$(count_docs "$WORK/list2")" ] && echo yes || echo no)"

# a document id that belongs to no document of this issue must be refused
R=$(api PUT "/issues/${ISSUE}/documents/${UNKNOWN_UUID}" '{"format":"markdown","body":"orphan\n"}')
kv f1_unknown_uuid_status "${R##* }"
cp "$WORK/body" "$WORK/unknownuuid"
kv f1_unknown_uuid_error "$(jget "$WORK/unknownuuid" error)"
kv f1_unknown_uuid_resolved_by "$(jget "$WORK/unknownuuid" details.resolvedBy)"

api GET "/issues/${ISSUE}/documents" - >/dev/null; cp "$WORK/body" "$WORK/list5"
kv f1_rows_final "$(count_docs "$WORK/list5")"
kv f1_orphan_row_created "$([ "$(count_docs "$WORK/list5")" -gt "$(count_docs "$WORK/list4")" ] && echo yes || echo no)"

# ------------------------------------------- Fault 2: PATCH carrying a
# reviewInteractionId without status: in_review must not answer 200 silently.
api GET "/issues/${ISSUE}" - >/dev/null; cp "$WORK/body" "$WORK/pre"
kv f2_title_before "DIG-2366 rehearsal probe"

# 2a — the canonical repro: the field on its own, nothing else.
R=$(api PATCH "/issues/${ISSUE}" '{"reviewInteractionId":"aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"}')
kv f2_only_interaction_status "${R##* }"
cp "$WORK/body" "$WORK/f2a"
kv f2_only_interaction_code "$(jget "$WORK/f2a" details.code)"
kv f2_only_interaction_error "$(jget "$WORK/f2a" error)"
kv f2_only_interaction_kinds "$(jget "$WORK/f2a" details.acceptedInteractionKinds | tr -d "[]' " | tr ',' ',')"
kv f2_only_interaction_changes "$(jget "$WORK/f2a" changes | tr -d '\n ')"

api GET "/issues/${ISSUE}" - >/dev/null; cp "$WORK/body" "$WORK/after2a"
kv f2_only_interaction_title_after "$(jget "$WORK/after2a" title)"

# 2b — the field alongside a real change: must be refused whole, not half applied.
R=$(api PATCH "/issues/${ISSUE}" '{"reviewInteractionId":"bbbbbbbb-cccc-4ddd-8eee-ffffffffffff","title":"probe title"}')
kv f2_with_title_status "${R##* }"
cp "$WORK/body" "$WORK/f2b"
kv f2_with_title_code "$(jget "$WORK/f2b" details.code)"

api GET "/issues/${ISSUE}" - >/dev/null; cp "$WORK/body" "$WORK/after2b"
kv f2_with_title_after "$(jget "$WORK/after2b" title)"

# a plain write must still work — the guard is not a blanket 422
R=$(api PATCH "/issues/${ISSUE}" '{"title":"probe title"}')
kv f2_plain_write_status "${R##* }"
cp "$WORK/body" "$WORK/plain"
kv f2_plain_write_changes "$(jget "$WORK/plain" changes | tr -d '\n ')"

api GET "/issues/${ISSUE}" - >/dev/null; cp "$WORK/body" "$WORK/after2c"
kv f2_title_final "$(jget "$WORK/after2c" title)"

kv issue_id_for_db "$ISSUE"
kv done yes
