# Parallel runbook — local session + Paperclip org

Board auth here is `local_trusted` (no token). Never use `$PAPERCLIP_API_KEY` in this session.

## Company ID

```bash
npx paperclipai company list 2>&1 | head
# or: ls ~/.paperclip/instances/default/companies/
# this machine: 3d7a91f3-c674-4a9e-862b-11b9698f6686 (prefix DIG)
```

## Monitor (read-only, always safe)

```bash
npx paperclipai issue list -C <company-id> --status todo,in_progress,blocked | head -n 50
npx paperclipai issue get <DIG-123> -C <company-id>
npx paperclipai issue comments <DIG-123> -C <company-id> | tail -n 40
npx paperclipai issue heartbeat-context <DIG-123> -C <company-id>
dt-mirror collect --json | head -c 2000   # your local git state, read-only
dt-mirror locks                           # files you have locked
```

## Capture (no wake)

```bash
npx paperclipai board prompt --title "Short title" --no-wake "What, why, links, acceptance criteria" -C <company-id>
```

## Run-it-here (claim as user)

```bash
npx paperclipai board prompt --title "Fix X" --no-wake "brief..." -C <company-id>
# note the returned identifier, e.g. DIG-1234
npx paperclipai issue comment DIG-1234 -C <company-id> --body "Claimed by Chris in local session twelve-x: DIG-1234-slug — agents skip"
# ... work on branch DIG-1234-slug ...
npx paperclipai issue work-product:create DIG-1234 -C <company-id> --json '{"type":"branch","url":"<branch-url>"}'
npx paperclipai issue update DIG-1234 -C <company-id> --status done --comment "Done: <what>. Verified by <gate/test>."
```

## Hand to org (wake an agent)

```bash
npx paperclipai board prompt --agent <shortname> --title "Title" "Full brief + acceptance criteria" -C <company-id>
# or append to existing issue and wake:
npx paperclipai board prompt --issue DIG-1234 "Additional context" -C <company-id>
npx paperclipai agent wake <shortname> -C <company-id>
```

## Parallel co-work (parent yours, child theirs)

```bash
~/paperclip-workspace/kit/bin/dt-create-issue --help  # agent-side creator; DO NOT use from here
# from here, children go through board auth:
npx paperclipai issue create -C <company-id> --title "Child: <scoped piece>" --description "Self-contained brief + links" --parent-id DIG-1234 --status todo
```

Parent stays user-owned; set `blockedBy` only via update with the child id when you truly wait.

## Stop rules

- `assigneeAgentId` set + checkout held by other agent → sibling, not steal.
- `in_review` with `monitorNextCheckAt` set → comment only, don't reset status.
- Same error 3x → file/keep `blocked` with what you tried, hand to owner.
- Budget >80% → critical tasks only; mentions (`@agent`) cost wakes, use sparingly.
