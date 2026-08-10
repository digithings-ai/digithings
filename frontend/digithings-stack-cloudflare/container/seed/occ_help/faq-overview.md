# Online Compliance Center — FAQ seed (static)

This note is a **minimal** digithings.ai/chat/occ grounding seed for the
Cloudflare Profile A stack. It is **not** a full crawl of
help.online-compliance-center.com (ingest HOLD — see
`docs/projects/online-compliance-center/GAPLOG.md`).

## What is OCC?

Online Compliance Center (OCC) helps organizations manage compliance policies,
procedures, and help-center documentation.

## How digithings chat helps

Ask questions about OCC policies and help articles. Answers are grounded on the
`occ_help` digisearch index and vault notes under
`clients/online-compliance-center/`.

## Replacing this seed

When crawl approval lands, run `scripts/docs_onboard/run_onboard.py` against
`docs/projects/online-compliance-center/onboard.yaml` targeting the production
digisearch + digivault volumes (or re-seed via Container SSH).
