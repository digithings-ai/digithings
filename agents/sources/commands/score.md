---
description: Run the 4-dimension scoring gate (Security/Quality/Optimization/Accuracy) on staged changes and walk fixes for any failure.
---

Run `make score` on the staged diff. If any dimension fails, read the corresponding `docs/scoring/<DIMENSION>.md` rubric and propose the narrowest fix for each finding. Stop after two iterations if the gate still fails and escalate.
