QA evidence (from the DIG-5134 acceptance run, develop tip 2a7e1ac74a, local dev servers; embed origin http://127.0.0.1:3005 so the frame really renders, dashboard parent 127.0.0.1:3111, origin inside DASHBOARD_DIGICHAT_FRAME_SRC).

Baseline tier (free, upgrade panel, no iframe):
- 390x844: section attr "upgrade", 0 iframes (correct), section box x=0 y=0 w=390 h=844, main box w=0. On screen: only the upgrade copy ("digichat unlocks with Desk", "Upgrade in Settings → Billing") and the digichat launcher; no app bar, no sidebar, no dashboard content at all.
- 1440x900: section x=298 w=1142 h=900, main w=38. On screen: sidebar normal, but the dashboard headings render one character per line in a 38px column and the upgrade copy sits at the top of the empty right area.

Entitled tier (live iframe):
- 390x844: section attr "live", 1 iframe, src http://127.0.0.1:3005/embed?host=digiquant.io&layout=embed&theme=dark&accent=%233dd6c4&welcome=Ask+about+this+page.&placeholder=ask+about+research+or+portfolio%E2%80%A6&suggestions=... On screen: the DigiChat embed renders in a 300x150 box (browser default) in the top right, over the mobile app bar; only "Ask about this page." and a clipped suggestion are visible, main squeezed to w=90.
- 1440x900: iframe 300x150 at x=1140 y=0, inside an unstyled 300px wide and 900px tall column at the top right; the embed is cut at 150px height so the input is not reachable and the rest of the page is empty.

Root cause: the section is an unstyled flex item in the AppFrame row (app-frame.tsx:53) with no width constraint, so it takes its max-content width (the upgrade paragraph) and squeezes main to nothing; the iframe carries no width/height, so it renders at the 300x150 browser default.

Suite state on develop: apps/dashboard/components/digichat-live-preview.test.tsx - 1 file, 2 tests, both pass. They assert markup only (section, iframe, upgrade copy), never layout, which is why this ships green.

Screenshots from the QA run: .qa/entitled-local-phone-390x844.png, .qa/entitled-local-desktop-1440x900.png, .qa/baseline-phone-390x844.png, .qa/baseline-desktop-1440x900.png (in the DIG-5134 worktree).
