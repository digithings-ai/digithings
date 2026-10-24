Review verdict: changes requested

QA acceptance of the shipped D8 DigiChat live preview on develop. Result: FAIL at both widths. The surface renders, the tier split is right and the frame origin is inside the allowlist, but the shipped layout takes the dashboard content column away from the user. Two defects filed as children of DIG-2698: DIG-5138 (layout, high, Frontend Engineer) and DIG-5139 (plan-tier handshake, medium, Frontend Engineer).

Blockers
1. apps/dashboard/components/digichat-live-preview.tsx:55-64 and apps/dashboard/components/app-frame.tsx:53 - the preview is an unstyled flex sibling of <main> inside <div className="flex min-h-screen">, with an iframe that carries no width/height. It takes its max-content width and squeezes <main> to 38px on desktop and 0px on phone. Detail and measurements in DIG-5138.
2. apps/dashboard/components/digichat-live-preview.tsx (no iframe ref, no effect, no postMessage) against apps/dashboard/components/digichat-popup.tsx:238-244 - the popup sends buildPlanTierMessage(tier, accessToken), the preview never does, so the embed can never mint the X-Embed-Plan-Proof that apps/digichat/src/app/api/chat/route.ts:344-379 requires when the tenant declares a gate. Detail in DIG-5139.

Checks from the card
1. Preview renders inside the AppFrame - PASS. Mounted at app-frame.tsx:53; apps/dashboard/lib/auth-gate.tsx:63 wraps every dashboard route in AppFrame, so it appears on every route, not only one.
2. Entitled tier gets the live DigiChat iframe, baseline tier gets the upgrade panel and no iframe - PASS. Entitled: section [data-digichat-live-preview="live"], exactly 1 iframe, no upgrade panel. Baseline (free): section [data-digichat-live-preview="upgrade"], 0 iframes, copy "digichat unlocks with Desk / House research and portfolio chat is a Desk feature. Upgrade to ask digichat about the house book and the page you are on." with the link "Upgrade in Settings → Billing" (href /settings#billing).
3. iframe origin stays inside DASHBOARD_DIGICHAT_FRAME_SRC - PASS. The built src is https://digithings.ai/embed?host=digiquant.io&layout=embed&theme=dark&accent=%233dd6c4&welcome=... and that origin is in the dashboard CSP frame-src list; no wildcard, no new origin, the production CSP header is unchanged. For the run I pointed the embed at a local digichat instance (http://127.0.0.1:3005, also in the list) so the frame really rendered instead of being blocked.
4. Same page at 390x844 and desktop - FAIL. Details below.

What was on screen
Phone 390x844, entitled tier: the DigiChat embed renders live in a 300x150 box in the top right (the browser default size), over the mobile app bar, showing "Ask about this page." and a clipped suggestion; the dashboard column next to it is squeezed to 90px.
Phone 390x844, baseline tier: the upgrade panel fills the whole 390x844 viewport (section x=0 w=390 h=844, main w=0); the screen shows only the upgrade copy and the digichat launcher - no app bar, no sidebar, no dashboard content.
Desktop 1440x900, entitled tier: the embed renders as a 300x150 iframe at the top right corner (x=1140 y=0) inside an empty 300px wide, 900px tall column; the embed is cut off at 150px height so the input is not reachable, and the rest of the page is empty.
Desktop 1440x900, baseline tier: the upgrade panel takes the right area (x=298 w=1142 h=900) and the dashboard column collapses to 38px; the headings render one character per line.

Evals
- npx vitest run components/digichat-live-preview.test.tsx in apps/dashboard on develop tip 2a7e1ac74a: 1 file, 2 tests, 2 passed. They assert markup only, never layout, which is why the defect ships green.
- Manual browser pass on a local dev server: dashboard on 127.0.0.1:3111 and digichat on 127.0.0.1:3005. Entitled tier with the dashboard auth flag off (tier resolves to enterprise); baseline tier with the auth flag on and a local fabricated free-tier session (localStorage sb-127-auth-token, plan_tier free, email qa-baseline@example.test). No production data was read or written.
- Full apps/dashboard unit suite on the same commit: 247 test files, 1942 tests, 1940 passed, 2 failed. The two failures are in components/app-shell-context.test.tsx (AppShellProvider sidebar storage - root.unmount of undefined at line 32), pre-existing on develop and unrelated to the live preview; components/digichat-live-preview.test.tsx passes 2/2. Log: .qa/dashboard-vitest-full.log in the DIG-5134 worktree.

Production note
The D8 live preview is not deployed yet: https://digiquant.io/dashboard/ (200) contains no iframe and no digichat-live-preview marker, only the older digichat popup. Nothing is broken in production - this is a develop-only defect, and it is exactly why the board could not certify the visual.

Local-only artifact, not a defect: with the default production embed origin, a local parent (127.0.0.1:3111) is refused by the production digichat frame-ancestors list, so the frame was blocked in the browser. The production parent digiquant.io is allowed.

Suggestions
1. Give the preview a bounded width and an explicit iframe size, and take it out of the content row on phone (stack it under the page content or a bottom sheet), so <main> keeps its width at every viewport.
2. Move the entitlement handshake into one shared helper the popup and the preview both call, so the plan-tier proof and the theme message cannot drift between the two surfaces.
3. Extend the component test with a width assertion on the preview container, so a layout regression fails the suite instead of the board.

Evidence on disk (local, QA worktree of DIG-5134): .qa/entitled-local-phone-390x844.png, .qa/entitled-local-desktop-1440x900.png, .qa/baseline-phone-390x844.png, .qa/baseline-desktop-1440x900.png. Copies kept at ~/Records/QA/DIG-5134/.

Next: DIG-5138 and DIG-5139 carry the fix under DIG-2698; QA re-verifies the same page at 390x844 and 1440x900 when they land.
