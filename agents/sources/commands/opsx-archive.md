---
description: Archive a completed OpenSpec change — merges delta specs into main specs and moves the change folder to archive/.
---

You are archiving a completed OpenSpec change.

Steps:
1. Find the change to archive: look for the most recently modified folder under `openspec/changes/` that is NOT inside `archive/`. If there are multiple, list them and ask which one to archive.
2. Read the change's delta specs at `openspec/changes/<slug>/specs/<domain>/spec.md`.
3. For each delta spec:
   - Open `openspec/specs/<domain>/spec.md`
   - Apply `## ADDED` entries by appending them to the appropriate section
   - Apply `## MODIFIED` entries by updating the existing requirement text
   - Apply `## REMOVED` entries by deleting those requirement lines
   - Save the updated spec file
4. Move the change folder to `openspec/changes/archive/<YYYY-MM-DD>-<slug>/` using today's date.
5. Verify the archive folder exists and the original path is gone.
6. Print which spec files were updated and confirm the archive location.
