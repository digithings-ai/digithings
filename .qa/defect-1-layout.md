QA acceptance on develop (DIG-5134) of the D8 live preview (PR #5838) fails on layout: the shipped preview is unstyled and takes the width away from the dashboard content column.

Ship: apps/dashboard/components/digichat-live-preview.tsx:55-64 renders the section with no class and an iframe with no width/height; apps/dashboard/components/app-frame.tsx:53 mounts it as a flex sibling of <main> inside <div className="flex min-h-screen">; apps/dashboard/lib/auth-gate.tsx:63 puts every dashboard route inside AppFrame, so it lands on every route.

Expected: a bounded, styled preview surface that does not take width from <main>, and an explicitly sized iframe so the embed is usable.
Acceptance: at 390x844 and 1440x900 the dashboard content column keeps its width, the embed input is reachable, no horizontal scrollbar; add a test that pins the container width so this cannot regress.
Measured evidence is in the first comment.
