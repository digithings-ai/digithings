Invoke the `ci-triage` skill on the specified PR (or the current branch's open PR if no number is given).

Steps:
1. Identify the PR number from the user's message, or detect it from the current branch.
2. Fetch the list of failing CI checks.
3. Bucket each failure: lint, format, doc-links, unit tests, PR linkage, scoring gate, Docker/compose, or other.
4. For each bucket, output the exact fix command.
5. Ask the user whether to apply the fixes immediately.
6. If yes, apply and push; if no, present the fix list for the user to run manually.
