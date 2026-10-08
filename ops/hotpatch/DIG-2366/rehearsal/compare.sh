#!/bin/bash
# DIG-2366 rehearsal — differential verdict.
#
# Reads results/control.txt and results/patched.txt and checks that the harness
# actually saw both faults in the control phase and that the patched phase
# removes them without regressing ordinary writes. Exits non-zero if any check
# fails, so the rehearsal cannot be reported green by accident.

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
RESULTS="$HERE/results"

val() { # val <file> <key>
  sed -n "s/^$2=//p" "$1" | head -1
}

CTL="$RESULTS/control.txt"
PTD="$RESULTS/patched.txt"
if [ ! -f "$CTL" ] || [ ! -f "$PTD" ]; then
  echo "missing transcripts: $CTL $PTD" >&2
  exit 2
fi

FAIL=0
check() { # check <description> <expected> <actual>
  if [ "$2" = "$3" ]; then
    printf '  PASS  %-62s %s\n' "$1" "$3"
  else
    printf '  FAIL  %-62s expected %s, got %s\n' "$1" "$2" "$3"
    FAIL=$((FAIL + 1))
  fi
}

printf '\n--- Fault 1: PUT /issues/:id/documents/:key addressed by a document id\n'
printf '  the harness must SEE the fault in the control phase\n'
check 'control: write by document id creates a row (201)'   201 "$(val "$CTL" f1_write_by_doc_id_status)"
check 'control: a second row appears'                        yes "$(val "$CTL" f1_second_row_created)"
check 'control: the document id is not addressable (404)'    404 "$(val "$CTL" f1_get_by_doc_id_status)"
check 'control: an unrelated uuid key is accepted (201)'     201 "$(val "$CTL" f1_unknown_uuid_status)"
check 'control: db row count after the write'                2    "$(val "$CTL" db_issue_documents_rows)"
printf '  the patched phase must close it\n'
check 'patched: write by document id updates in place (200)' 200  "$(val "$PTD" f1_write_by_doc_id_status)"
check 'patched: no second row'                               no   "$(val "$PTD" f1_second_row_created)"
check 'patched: rows unchanged across the write'             "$(val "$PTD" f1_rows_after_seed)" "$(val "$PTD" f1_rows_after_write_by_doc_id)"
check 'patched: db row count stays at one'                   1    "$(val "$PTD" db_issue_documents_rows)"
check 'patched: the document id resolves to the same row'    yes  "$(val "$PTD" f1_get_by_doc_id_same)"
check 'patched: the write landed on the original key'        spec "$(val "$PTD" f1_write_by_doc_id_key)"
check 'patched: an unrelated uuid key is refused (409)'      409  "$(val "$PTD" f1_unknown_uuid_status)"
check 'patched: the refusal names documents.id'             documents.id "$(val "$PTD" f1_unknown_uuid_resolved_by)"

printf '\n--- Fault 2: PATCH /api/issues/:id carrying reviewInteractionId without in_review\n'
printf '  2a, the canonical repro: the field on its own\n'
check 'control: answers 200'                                 200  "$(val "$CTL" f2_only_interaction_status)"
check 'control: answers with an EMPTY changes map'           '{}'  "$(val "$CTL" f2_only_interaction_changes)"
printf '  the patched phase must close it\n'
check 'patched: answers 422'                                 422  "$(val "$PTD" f2_only_interaction_status)"
check 'patched: names the rule'                              review_interaction_requires_in_review "$(val "$PTD" f2_only_interaction_code)"
check 'patched: names the accepted kinds'                    'request_confirmation,request_checkbox_confirmation' "$(val "$PTD" f2_only_interaction_kinds)"
printf '  2b, the field alongside a real change: refused whole, not half applied\n'
check 'control: answers 200'                                 200  "$(val "$CTL" f2_with_title_status)"
check 'control: the accompanying title is applied'           'probe title' "$(val "$CTL" f2_with_title_after)"
check 'patched: answers 422'                                 422  "$(val "$PTD" f2_with_title_status)"
check 'patched: the accompanying title is not applied'       'DIG-2366 rehearsal probe' "$(val "$PTD" f2_with_title_after)"

printf '\n--- no regression on ordinary writes\n'
check 'control: plain PATCH still 200'                       200 "$(val "$CTL" f2_plain_write_status)"
check 'patched: plain PATCH still 200'                       200 "$(val "$PTD" f2_plain_write_status)"
check 'patched: plain PATCH reports its change'              'probe title' "$(val "$PTD" f2_title_final)"
check 'patched: the plain PATCH changes map is not empty'    yes "$([ "$(val "$PTD" f2_plain_write_changes)" != '{}' ] && [ -n "$(val "$PTD" f2_plain_write_changes)" ] && echo yes || echo no)"
check 'patched: the seed document write still 201'           201 "$(val "$PTD" f1_seed_status)"
check 'both: the seed document write was 201'                201 "$(val "$CTL" f1_seed_status)"

printf '\n'
if [ "$FAIL" -eq 0 ]; then
  printf 'REHEARSAL VERDICT: pass — every check above held in both phases\n'
  exit 0
fi
printf 'REHEARSAL VERDICT: FAIL — %s check(s) did not hold\n' "$FAIL"
exit 1
