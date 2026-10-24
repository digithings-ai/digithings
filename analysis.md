## Verdict
MATCHES

## Per-row table
| row id | workflow | declared inputs | row static inputs | kickArgs | ok? |
|---|---|---|---|---|---|
| continuous-improvement | pipeline-continuous-improvement.yml | start_key | none | ["start_key"] | ok |
| maintenance | pipeline-maintenance.yml | start_key | none | ["start_key"] | ok |
| provider-review | pipeline-provider-review.yml | start_key | none | ["start_key"] | ok |
| agent-pr-finalizer | agent-pr-finalizer.yml | dry_run, start_key | {dry_run: "false"} | ["start_key"] | ok |
| agent-backlog-snapshot | agent-backlog-snapshot.yml | start_key | none | ["start_key"] | ok |
| ci-pr-hygiene | ci-pr-hygiene.yml | start_key | none | ["start_key"] | ok |
| refresh-repo-activity | refresh-repo-activity.yml | start_key | none | ["start_key"] | ok |
| project-enforce-assignment | project-enforce-assignment.yml | start_key | none | ["start_key"] | ok |
| security-pip-audit | security-pip-audit.yml | start_key | none | ["start_key"] | ok |
| security-npm-audit | security-npm-audit.yml | start_key | none | ["start_key"] | ok |
| token-canary | token-canary.yml | start_key | none | ["start_key"] | ok |
| secret-staleness | secret-staleness-check.yml | max_age_days | none | ["max_age_days"] | ok |
| twelve-x-asia | daily_run_asia.yml | (none) | none | [] | ok |
| twelve-x-london | daily_run_london.yml | (none) | none | [] | ok |
| twelve-x-new-york | daily_run_new_york.yml | (none) | none | [] | ok |
| twelve-x-market-context-intraday | market_context_ingest.yml | bucket (choice, required) | {bucket: "intraday"} | [] | ok |
| twelve-x-market-context-daily | market_context_ingest.yml | bucket (choice, required) | {bucket: "daily"} | [] | ok |
| twelve-x-market-context-weekly | market_context_ingest.yml | bucket (choice, required) | {bucket: "weekly"} | [] | ok |
| twelve-x-performance-eval | performance_eval.yml | since | none | ["since"] | ok |
| twelve-x-primemarket-heartbeat | primemarket_session_heartbeat.yml | (none) | none | [] | ok |
| twelve-x-session-catchup | session_catchup.yml | (none) | none | [] | ok |
| twelve-x-archive-maintenance | archive_maintenance.yml | task, dry_run, hot_days, dump_before_prune | {dry_run: "false", dump_before_prune: "true"} | ["task", "hot_days"] | ok |
| twelve-x-digisearch-parity | digisearch_parity_check.yml | days (optional, default "14") | none | ["days"] | ok |
| twelve-x-snapshot-backfill | maintenance.yml (twelve-x) | backfill_snapshots, since | {backfill_snapshots: "true"} | ["since", "dates", "until"] | ok |

## Mismatches
none