#!/usr/bin/env bash
# Golden questions on FREE models only. usage: tests/run_qa.sh all|QID...
# Stops on the first rate-limit (429) round: retrying burns the free quota.
# The model runner is the client's choice (e.g. an OpenCode agent in tests/qa/);
# the template ships the loop and the stop rule only.
set -uo pipefail
cd "$(dirname "$0")"
MODELS="${QA_MODELS:-}"   # comma-separated FREE model ids
[ -n "$MODELS" ] || { echo "set QA_MODELS to free model ids (paid models are not allowed)" >&2; exit 2; }
ids=("$@"); [ "${ids[0]:-all}" = all ] && mapfile -t ids < <(python3 -c 'import json;[print(q["id"]) for q in json.load(open("questions.json"))]')
mkdir -p qa/runs
for id in "${ids[@]}"; do
  q=$(python3 -c 'import json,sys;print(next(x["question"] for x in json.load(open("questions.json")) if x["id"]==sys.argv[1]))' "$id")
  IFS=, read -ra ms <<< "$MODELS"; limited=0
  for m in "${ms[@]}"; do
    if ! command -v qa_run >/dev/null; then echo "define qa_run MODEL QUESTION (see tests/qa/)" >&2; exit 2; fi
    qa_run "$m" "$q" > "qa/runs/$id.out" 2> "qa/runs/$id.err"
    if grep -qiE "429|usage limit|rate limit" "qa/runs/$id.err" "qa/runs/$id.out"; then limited=$((limited+1)); continue; fi
    echo "$id $m done"; break
  done
  [ "$limited" -ge "${#ms[@]}" ] && { echo "STOP: every free model returned a rate limit on $id" >&2; exit 3; }
done
