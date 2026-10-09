#!/bin/bash
# dt-routine-watch: a schedule boundary that passed with no firing must file, and must not file twice,
# and a manual probe must never be mistaken for a firing (DIG-1220).
# No network: --fixtures feeds the script JSON files standing in for the routines API, and --dry
# prints the page it would file instead of filing it.
# CI: pytest wrapper tests/scripts/test_dt_routine_watch.py under the ruff-and-scripts lane.
#
# The script under test has one home: ~/paperclip-workspace/kit/bin/dt-routine-watch. Paperclip is
# loopback-only, so the observer must be host-resident, and the kit is already where every other
# operational script lives (dt-books, dt-cron, dt-merge-queue, dt-gate, dt-snapshot, dt-keys,
# dt-backup). This repo once carried a second copy of the observer; it had already drifted away from
# the running one, which is the exact failure mode DIG-1220 exists to catch, so it was removed
# (DIG-2618). Do not add it back.
#
# The suite still has two homes -- the kit (tests/dt-routine-watch-test.sh) and this repo
# (tests/scripts/test_dt_routine_watch.sh) -- and still one body, because a forked suite would be a
# second thing to forget to update. Only this header differs. Both candidates below resolve to that
# one canonical script: the relative one when the suite runs from the kit, the $HOME one when it
# runs from here. Neither of them is a copy in this repo. If the script is missing the suite must
# fail, so a missing subject can never read as a passing run.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
WATCH=""
for candidate in "$HERE/../bin/dt-routine-watch" "${HOME:-/nonexistent}/paperclip-workspace/kit/bin/dt-routine-watch"; do
  if [ -x "$candidate" ]; then WATCH="$candidate"; break; fi
done
if [ -z "$WATCH" ]; then
  printf 'FAIL cannot find dt-routine-watch (looked in the kit home and $HOME/paperclip-workspace/kit)\n'
  printf '\n1 check(s) failed\n'
  exit 1
fi
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dt-routine-watch-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
fails=0

ok() { printf 'ok   %s\n' "$1"; }
no() { # a failure must show what the script actually said, or it is just a guess
  printf 'FAIL %s\n' "$1"; fails=$((fails+1))
  [ -n "${DEBUG:-}" ] && printf '%s\n' "${OUT:-<no output captured>}" | sed 's/^/    | /'
  return 0
}

CO="3d7a91f3-c674-4a9e-862b-11b9698f6686"
RID="30c5db5f-fe59-4464-b784-6fe6f741f680"
TID="9714a360-9b76-4e4e-84c0-6c84da6c2826"
OWNER="a7bf824b-12fb-45a7-9c0e-80d46f0cfabd"

# fixture <dir> <boundary> <lastFiredAt> <lastResult> [runs-json]
fixture() { # a company routines list plus a run history, as the API would return them
  mkdir -p "$1"
  python3 - "$1" "$2" "$3" "$4" "$5" <<'PY'
import json, sys
d, boundary, fired, result, runs = sys.argv[1:6]
json.dump([{
  "id": "30c5db5f-fe59-4464-b784-6fe6f741f680",
  "name": "twelve-x: confirm daily that the research feed published what it should have",
  "status": "active",
  "assigneeAgentId": "a7bf824b-12fb-45a7-9c0e-80d46f0cfabd",
  "concurrencyPolicy": "coalesce_if_active",
  "catchUpPolicy": "skip_missed",
  "triggers": [{
    "id": "9714a360-9b76-4e4e-84c0-6c84da6c2826",
    "kind": "schedule", "enabled": True, "archived": False,
    "cronExpression": "0 9 * * *", "timezone": "UTC",
    "nextRunAt": boundary, "lastFiredAt": fired, "lastResult": result,
  }],
}], open(d + "/companies_" + "3d7a91f3-c674-4a9e-862b-11b9698f6686" + "_routines.json", "w"))
json.dump(json.loads(runs) if runs else [], open(d + "/routines_" + "30c5db5f-fe59-4464-b784-6fe6f741f680" + "_runs.json", "w"))
PY
}

conf() { # conf <path> <extra-json-fragment-ending-in-a-comma-or-empty>
  printf '{"api":"http://127.0.0.1:3100/api","companyId":"%s","parentIssueId":"c6ee2d0e-1692-4149-ace5-5a72bd0c413e","goalId":"3098d6bd-e88a-4de0-acd1-a537ac2de838","defaultOwnerAgentId":"%s",%s"watch":[{"routineId":"%s","triggerId":"%s","ownerAgentId":"%s","note":"twelve-x daily feed confirm"}]}' \
    "$CO" "$OWNER" "${2:-}" "$RID" "$TID" "$OWNER" > "$1"
  python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$1" \
    || { printf 'harness bug: %s is not valid JSON\n' "$1"; exit 99; }
}

run() { # run <name> <fixturedir> <state> [conf-extra]
  conf "$WORK/c.json" "${4:-}"
  "$WATCH" --dry --fixtures "$2" --config "$WORK/c.json" --state "$3" > "$WORK/out.txt" 2>&1
  OUT="$(cat "$WORK/out.txt")"
  printf '%s' "$OUT" | grep -q "DRY POST" && PAGES=1 || PAGES=0
}

SCHED_RUN='[{"id":"r1","triggeredAt":"2026-10-06T09:00:04.000Z","source":"schedule","triggerId":"9714a360-9b76-4e4e-84c0-6c84da6c2826","status":"succeeded"}]'
MANUAL_RUN='[{"id":"r2","triggeredAt":"2026-10-06T09:02:00.000Z","source":"manual","triggerId":null,"status":"failed"}]'
TWO_MANUAL='[{"id":"r1","triggeredAt":"2026-10-05T17:48:47.526Z","source":"manual","triggerId":null,"status":"failed"},{"id":"r2","triggeredAt":"2026-10-06T09:02:00.000Z","source":"manual","triggerId":null,"status":"failed"}]'

# 1. the boundary is still in the future: nothing is due, nothing is filed
PAST=$(python3 -c 'import datetime;print((datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z"))')
fixture "$WORK/f1" "$PAST" null null "$TWO_MANUAL"
run 1 "$WORK/f1" "$WORK/s1.json"
[ "$PAGES" = 0 ] && printf '%s' "$OUT" | grep -q "not yet due" \
  && ok "a boundary inside the grace period is not judged" \
  || no "a boundary inside the grace period is not judged"

# 2. the routine fired on schedule: a run exists at the boundary, nothing is filed
DUE=$(python3 -c 'import datetime;print((datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z"))')
fixture "$WORK/f2" "$DUE" "$DUE" "ok" "$SCHED_RUN"
run 2 "$WORK/f2" "$WORK/s2.json"
[ "$PAGES" = 0 ] && printf '%s' "$OUT" | grep -q "ok" \
  && ok "a schedule run at the boundary is silent (no false page)" \
  || no "a schedule run at the boundary is silent (no false page)"

# 3. THE CASE THIS EXISTS FOR: the boundary passed and nothing fired anywhere
fixture "$WORK/f3" "$DUE" null null "$TWO_MANUAL"
run 3 "$WORK/f3" "$WORK/s3.json"
[ "$PAGES" = 1 ] && printf '%s' "$OUT" | grep -q "missed" \
  && ok "a passed boundary with no firing files an issue" \
  || no "a passed boundary with no firing files an issue"

# 4. and it files exactly once: the same boundary must not page again on the next tick
run 4 "$WORK/f3" "$WORK/s3.json"
[ "$PAGES" = 0 ] \
  && ok "the same boundary does not page twice" \
  || no "the same boundary does not page twice"

# 5. a manual probe after the boundary is NOT evidence of a firing. Two runs exist and are recent;
#    if manual counted, the false negative this was filed for would still be there.
fixture "$WORK/f5" "$DUE" null null "$MANUAL_RUN"
run 5 "$WORK/f5" "$WORK/s5.json"
[ "$PAGES" = 1 ] && printf '%s' "$OUT" | grep -q "missed" \
  && ok "a manual probe never satisfies a boundary" \
  || no "a manual probe never satisfies a boundary"

# 6. coalesce: the scheduler recorded the firing and said why, so this is a record, not silence
FIX="$DUE"
FIR="$(python3 -c 'import datetime;print((datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=2,minutes=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"))')"
fixture "$WORK/f6" "$FIX" "$FIR" "Skipped because a live execution issue already exists" "$TWO_MANUAL"
run 6 "$WORK/f6" "$WORK/s6.json"
[ "$PAGES" = 0 ] && printf '%s' "$OUT" | grep -q "coalesce" \
  && ok "one coalesced boundary is recorded, not paged" \
  || no "one coalesced boundary is recorded, not paged"

# 7. a streak of them means the clock turns and nothing is achieved: that gets paged.
#    Three ticks, three different boundaries, state carried forward untouched, so the streak builds.
rm -f "$WORK/s7.json"
for i in 1 2 3; do
  B="$(python3 -c "import datetime;print((datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=$((i*2)))).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")"
  F="$(python3 -c "import datetime;print((datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=$((i*2)),minutes=1)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")"
  fixture "$WORK/f7" "$B" "$F" "Skipped because a live execution issue already exists" "$TWO_MANUAL"
  run 7 "$WORK/f7" "$WORK/s7.json" '"skipStreakBeforeFiling":3,'
done
[ "$PAGES" = 1 ] && printf '%s' "$OUT" | grep -q "coalesced" \
  && ok "a streak of coalesced boundaries pages" \
  || no "a streak of coalesced boundaries pages"

# 8. the clock's own silence: state says the last check was five hours ago
fixture "$WORK/f8" "$DUE" null null "$TWO_MANUAL"
python3 -c "
import datetime, json
old=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=5)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
json.dump({'lastCheckAt':old,'boundaries':{}}, open('$WORK/s8.json','w'))
"
run 8 "$WORK/f8" "$WORK/s8.json"
printf '%s' "$OUT" | grep -q "kind=self-gap" \
  && ok "the watchdog pages on its own silence" \
  || no "the watchdog pages on its own silence"

# 9. and reports its own failed lookup instead of swallowing it. Tick 1 cannot read the routines
#    API at all; tick 2 reads it again and reports the outage that tick 1 could not report itself,
#    because filing an issue is itself an API call.
rm -f "$WORK/s9.json"
mkdir -p "$WORK/f9"
conf "$WORK/c9.json" '"maxApiGapSeconds":300,'
# The API was last read successfully 20 minutes ago. The threshold is 5 minutes, so the outage is
# already old enough to be worth reporting -- but filing an issue is itself an API call, so the
# watchdog can only note it now and report it once the API answers.
python3 -c "
import datetime, json
ago=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=20)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
json.dump({'lastApiOkAt':ago,'lastCheckAt':ago,'boundaries':{},'apiFailures':0}, open('$WORK/s9.json','w'))
"
# tick 1: the routines API cannot be read at all
OUT="$("$WATCH" --dry --fixtures "$WORK/f9" --config "$WORK/c9.json" --state "$WORK/s9.json" 2>&1)"
PAGES=0
printf '%s' "$OUT" | grep -q "DRY POST" && PAGES=1
if [ "$PAGES" = 0 ] && python3 -c "
import json,sys
st=json.load(open(sys.argv[1]))
sys.exit(0 if st.get('apiGapReportedAt') and st.get('apiFailures')==1 else 1)
" "$WORK/s9.json"; then
  ok "an API too long unreadable is remembered, not reported while it is still down"
else
  no "an API too long unreadable is remembered, not reported while it is still down"
fi
# tick 2: the API answers again, and the outage that tick 1 could not report is reported now
printf '%s' '[{"id":"30c5db5f-fe59-4464-b784-6fe6f741f680","triggers":[]}]' > "$WORK/f9/companies_${CO}_routines.json"
run 9 "$WORK/f9" "$WORK/s9.json" '"maxApiGapSeconds":300,'
[ "$PAGES" = 1 ] && printf '%s' "$OUT" | grep -q "kind=api-gap" \
  && ok "the watchdog pages on its own lookup failing once it can" \
  || no "the watchdog pages on its own lookup failing once it can"

# 10. no watch list is a loud failure, not a silent pass
printf '{"companyId":"x","watch":[]}' > "$WORK/c10.json"
"$WATCH" --dry --config "$WORK/c10.json" --state "$WORK/s10.json" >/dev/null 2>&1
[ $? -ne 0 ] && ok "an empty watch list exits non-zero" || no "an empty watch list exits non-zero"

# 11. watchAllScheduleTriggers derives the watch list from the board, so a routine created tomorrow
#     is watched tomorrow, and only the routines that could actually fire are included.
mkdir -p "$WORK/f11"
python3 - "$WORK/f11" "$DUE" "$CO" <<'PY'
import json, sys
d, due, co = sys.argv[1:4]
def trig(tid, **kw):
    t = {"id": tid, "kind": "schedule", "enabled": True, "archived": False,
         "cronExpression": "0 9 * * *", "nextRunAt": due, "lastFiredAt": None, "lastResult": None}
    t.update(kw)
    return t
json.dump([
  # watched: active, scheduled, enabled, not archived, has a boundary
  {"id": "r-active", "name": "active routine", "status": "active", "assigneeAgentId": "agent-active",
   "triggers": [trig("t-active")]},
  # not watched: a paused routine is not expected to fire, so paging it would be noise
  {"id": "r-paused", "name": "paused routine", "status": "paused", "assigneeAgentId": "agent-paused",
   "triggers": [trig("t-paused")]},
  # not watched: the trigger is switched off
  {"id": "r-disabled", "name": "disabled trigger", "status": "active", "assigneeAgentId": "agent-a",
   "triggers": [trig("t-disabled", enabled=False)]},
  # not watched: archived
  {"id": "r-archived", "name": "archived trigger", "status": "active", "assigneeAgentId": "agent-a",
   "triggers": [trig("t-archived", archived=True)]},
  # not watched: no nextRunAt means no claim to falsify
  {"id": "r-noboundary", "name": "no boundary", "status": "active", "assigneeAgentId": "agent-a",
   "triggers": [trig("t-noboundary", nextRunAt=None)]},
  # not watched: a non-schedule trigger has no boundary to judge
  {"id": "r-manual", "name": "manual trigger", "status": "active", "assigneeAgentId": "agent-a",
   "triggers": [{"id": "t-manual", "kind": "manual", "enabled": True, "nextRunAt": due}]},
  # not watched: a routine with no schedule trigger at all
  {"id": "r-empty", "name": "no triggers", "status": "active", "assigneeAgentId": "agent-a",
   "triggers": []},
], open(d + "/companies_" + co + "_routines.json", "w"))
PY
printf '{"api":"http://127.0.0.1:3100/api","companyId":"%s","parentIssueId":"c6ee2d0e-1692-4149-ace5-5a72bd0c413e","goalId":"3098d6bd-e88a-4de0-acd1-a537ac2de838","watchAllScheduleTriggers":true,"watch":[]}' "$CO" > "$WORK/c11.json"
OUT="$("$WATCH" --dry --fixtures "$WORK/f11" --config "$WORK/c11.json" --state "$WORK/s11.json" 2>&1)"
if printf '%s' "$OUT" | grep -q "watching 1 routine(s): 0 configured, 1 derived from the board" \
   && printf '%s' "$OUT" | grep -q "r-active" \
   && printf '%s' "$OUT" | grep -q "checked 1 watch(es)"; then
  ok "watchAllScheduleTriggers watches only routines that could fire, read from the board"
else
  no "watchAllScheduleTriggers watches only routines that could fire, read from the board"
fi

# 12. and the derived watch pages on its own routine, with that routine's owner and name
printf '[]' > "$WORK/f11/routines_r-active_runs.json"
OUT="$("$WATCH" --dry --fixtures "$WORK/f11" --config "$WORK/c11.json" --state "$WORK/s11b.json" 2>&1)"
printf '%s' "$OUT" | grep -q "DRY POST" && printf '%s' "$OUT" | grep -q "active routine" \
  && ok "a derived watch files a page naming that routine" \
  || no "a derived watch files a page naming that routine"

# 13. an explicit entry wins over the derived one for the same trigger, and is not double-watched
printf '{"api":"http://127.0.0.1:3100/api","companyId":"%s","parentIssueId":"c6ee2d0e-1692-4149-ace5-5a72bd0c413e","goalId":"3098d6bd-e88a-4de0-acd1-a537ac2de838","watchAllScheduleTriggers":true,"watch":[{"routineId":"r-active","triggerId":"t-active","ownerAgentId":"a7bf824b-12fb-45a7-9c0e-80d46f0cfabd","note":"my own note"}]}' "$CO" > "$WORK/c13.json"
OUT="$("$WATCH" --dry --fixtures "$WORK/f11" --config "$WORK/c13.json" --state "$WORK/s13.json" 2>&1)"
if printf '%s' "$OUT" | grep -q "watching 1 routine(s): 1 configured, 1 derived from the board" \
   && printf '%s' "$OUT" | grep -q "my own note"; then
  ok "an explicit entry is not double-watched and keeps its own note"
else
  no "an explicit entry is not double-watched and keeps its own note"
fi

# 14. watchAllScheduleTriggers matching nothing is loud, not a silent pass: the API answering with
#     an empty company must not read as "every routine is fine". This is distinct from case 9: there
#     the read fails and the api-gap path owns the outcome; here the read succeeds and finds nothing.
mkdir -p "$WORK/f14"
printf '[]' > "$WORK/f14/companies_nothing-here_routines.json"
printf '{"api":"http://127.0.0.1:3100/api","companyId":"nothing-here","watchAllScheduleTriggers":true,"watch":[]}' > "$WORK/c14.json"
"$WATCH" --dry --fixtures "$WORK/f14" --config "$WORK/c14.json" --state "$WORK/s14.json" >/dev/null 2>&1
[ $? -ne 0 ] && ok "watchAllScheduleTriggers matching nothing exits non-zero" \
  || no "watchAllScheduleTriggers matching nothing exits non-zero"

if [ "$fails" -eq 0 ]; then printf '\nall checks passed\n'; else printf '\n%s check(s) failed\n' "$fails"; fi
exit $([ "$fails" -eq 0 ] && echo 0 || echo 1)