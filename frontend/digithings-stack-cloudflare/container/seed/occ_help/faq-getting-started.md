# OCC getting started (seed)

## Who this assistant is for

Staff and operators using digithings.ai/chat/occ to look up Online Compliance
Center help topics without logging into the customer portal.

## Typical first questions

1. What is Online Compliance Center?
2. Where do I find policies vs procedures?
3. How are PDF help documents handled?
4. What is out of scope (e-learning, portal, demo)?

## How to ask good questions

- Name the topic (e.g. “document retention policy”, “onboarding procedure”)
- Ask for steps or definitions rather than legal advice
- Expect citations to help articles or vault paths when available

## Replacing this seed

After crawl approval, run `scripts/docs_onboard/run_onboard.py` against
`docs/projects/online-compliance-center/onboard.yaml` targeting production
digisearch + digivault (or re-seed via Container ops).
