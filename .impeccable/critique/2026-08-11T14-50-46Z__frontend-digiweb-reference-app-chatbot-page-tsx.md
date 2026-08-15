---
target: digichat /chatbot reference surface
total_score: 33
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
timestamp: 2026-08-11T14-50-46Z
slug: frontend-digiweb-reference-app-chatbot-page-tsx
---
Method: dual-agent (A: design-review subagent · B: detector+browser-evidence subagent — isolated, run in parallel via Workflow)

#### Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Tool/thinking status glyphs are clear, but no shipped example ever shows a call in its live "running" state — the one state a multi-second backtest most needs to prove out. |
| 2 | Match System / Real World | 4 | Vocabulary (PF, Sharpe, maxDD, Kelly cap, maker/taker) and the CLI metaphor match the stated Claude-Code/opencode-literate audience precisely. |
| 3 | User Control and Freedom | 3 | Good micro-controls (Shift+Enter, per-call collapse, approval reset link) but no shown way to cancel/interrupt an in-flight tool call. |
| 4 | Consistency and Standards | 4 | One glyph/one meaning, one accent at a time, every embedded object converges on `ChatWidgetFrame` — confirmed across every reference file and its canonical `@digithings/web` component. |
| 5 | Error Prevention | 2 | The Approve/Decline buttons on the live-order approval gate have no `:disabled` visual treatment anywhere in `chat-widgets.css` — the single highest-stakes control has no double-submit guard. |
| 6 | Recognition Rather Than Recall | 3 | The `>`/`▸`/`·` marker system carries real meaning with zero on-page legend. |
| 7 | Flexibility and Efficiency | 4 | Slash commands, keyboard send, collapse-by-default chains — the right default for a power-user audience. |
| 8 | Aesthetic and Minimalist Design | 4 | Single accent, mono workhorse type, zero decorative color noise — monochrome-by-default executed with real discipline. |
| 9 | Error Recovery | 4 | The failed `digikey.exchange` call is exemplary: down-colored, paired with the exact fix command, restated in plain language. |
| 10 | Help and Documentation | 2 | No discoverable help/glossary for jargon-dense vocabulary beyond a static "/ commands" hint. |
| **Total** | | **33/40** | **Good** |

#### Design Specificity Verdict

**LLM assessment**: Authored specifically for this product, not a reskinned generic chat template. The demo data is real quant vocabulary (`trend_xsec`, Kelly-cap 0.5×, walk-forward windows, PF/Sharpe/maxDD), the tool names are the product's actual internal services (`digiquant.backtest`, `digisearch.query`, `digikey.exchange`) wired to a real failure mode with a real fix command, the route-graph diagrams this system's own supervisor→sub-graph→vault architecture, and the color system enforces the documented "money and code colors stay quarantined" rule as a concrete decision (the equity curve uses the identity accent, never P&L red/green). The human-approval gate for live orders is the strongest tell — it's the literal enactment of this repo's own non-negotiable rule never to touch live-trading paths without human approval. None of this transplants cleanly into a generic AI-chat product.

**Deterministic scan**: `detect.mjs` ran clean — exit 0, zero findings — over the three chatbot-scoped directories. But its scope didn't include `site-nav.tsx` or the shared `globals.css`/`chat-core.css`/`web-theme.css` files, which is exactly where the real defects below live. A clean detector run here means "no known anti-pattern regex matched," not "no problems" — worth remembering before treating exit 0 as a clean bill of health.

**Visual overlays**: Browser automation was flaky mid-session (the pane repeatedly reported "hidden," screenshots returned solid-black or double-exposed frames, tabs were recycled unexpectedly) — no reliable visual overlay is available. Assessment B compensated with direct DOM/`getBoundingClientRect` queries instead, which is how the two confirmed findings below were actually measured (more reliable than the flaky screenshot path this session, if less visual).

#### Overall Impression

A genuinely disciplined, product-specific design system executed with real restraint — the monochrome-by-default terminal aesthetic, the glyph-not-color role signal, and the quarantined color domains are all *enforced*, not just asserted. The single biggest opportunity is closing the gap between "the system is well-designed" and "the reference page proves it": the specimen never demonstrates its own most important state (a call actually running), and a genuinely reproducible mobile-layout bug means a phone visitor can't even navigate away from the page.

#### What's Working

- **Domain-authentic error recovery**: the failed `digikey.exchange` call renders in the down color, keeps the exact remediation command inline, and the assistant's own prose separates what succeeded from what's blocked — real actionable recovery, not a generic "something went wrong."
- **Disciplined color economy, independently verified**: Assessment B confirmed via source that tool-call status uses distinct glyphs (`…`/`✓`/`✕`) *plus* distinct `text-up`/`text-down` classes — not color alone — and that a site-wide `:focus-visible` rule (`web-theme.css:60`) covers every chat control with no suppressing override. Three plausible a11y complaints (unlabeled icon buttons, color-only status, invisible focus rings) were checked and refuted with concrete evidence rather than assumed.
- **Reduced-motion handling is unusually thorough**: thinking-chain reveal, route-graph draw, running-call pulse, and think-dot pulse all carry explicit `prefers-reduced-motion` overrides — most reference implementations skip this.

#### Priority Issues

- **[P1] Mobile hamburger nav trigger is completely unreachable at ≤375px.** Assessment A spotted it visually; Assessment B root-caused and measured it precisely: `site-nav.tsx`'s `ResizeObserver` collapse logic only toggles the page-link list, never accounting for the "Page livery" and "Type suite" `<select>` pickers, which stay unconditionally rendered — and `.site-nav { overflow: clip }` silently clips the overflow instead of wrapping. Measured via `getBoundingClientRect`: the "Open navigation" button sits entirely beyond the 375px viewport edge, with no horizontal scroll to reveal it. A phone visitor literally cannot open the section nav.
  **Fix**: collapse the two selects into the hamburger drawer (or shrink to icon-only) below a breakpoint so the nav toggle always stays inside the viewport.
  **Suggested command**: `/impeccable layout`

- **[P1] Live-order Approve/Decline buttons have no `:disabled` treatment.** Confirmed in source: none of `ChatWidgetButton`'s three tones carry a `:disabled` rule in `chat-widgets.css` (only `.cw-btn--primary` gets a special color at all). This is the button family used for the single highest-stakes action on the page — approving a live order — with no visual guard against a double-submit.
  **Fix**: add opacity/pointer-events treatment for `:disabled` across all three `.cw-btn` tones, matching what `.composer-send:disabled` already does correctly.
  **Suggested command**: `/impeccable harden`

- **[P2] Heading hierarchy skips a level (H2 → H4, no H3 between).** Confirmed via DOM query: the last H2 ("Answers you can act on") is directly followed by two H4s with no intervening H3 — a WCAG 2.4.6/1.3.1 best-practice violation the detector's regex scan didn't catch.
  **Fix**: insert the missing H3 level or demote the two H4s to H3.
  **Suggested command**: `/impeccable audit`

- **[P2] "Copy code" button fails the WCAG 2.5.8 24×24px minimum touch target.** Confirmed via source + live measurement: `.chat-md-copy` sets no padding or min-size, rendering at ~27×16px — the 16px height fails the AA minimum.
  **Fix**: pad the hit area to at least 24×24px without changing the visible label size.
  **Suggested command**: `/impeccable audit`

- **[P2] No shipped example ever shows a tool-call or thinking-chain in its live "running" state.** Every example on the page loads already resolved (ok or error) — for a surface whose core value is watching an agent work through a possibly long-running backtest, the state a user most needs reassurance about is exactly the one the reference never proves out.
  **Fix**: add a fourth example frozen in the running state, or auto-advance one call through running→ok on a timer.
  **Suggested command**: `/impeccable harden`

- **[P2] Composer tray has no responsive wrap rule and risks crowding.** `.composer-tray` packs five elements (attach icon, model pill, "/ commands" hint, char counter, send button) into one flex row with no `flex-wrap` or breakpoint override — notably, the *same page*'s metrics grid already carries a working `max-[560px]:grid-cols-2` mobile rule, making this read as an oversight rather than a constraint.
  **Fix**: add a narrow-viewport wrap or progressive-hide rule (e.g. hide the "/ commands" hint below ~420px), consistent with the pattern already used elsewhere on the same page.
  **Suggested command**: `/impeccable layout`

- **[P3] No on-page legend for the `>`/`▸`/`·` marker system.** The glyphs carry real, documented meaning (DESIGN.md's "one glyph, one meaning" rule) but a first-time visitor must infer the rule purely from repeated exposure.
  **Fix**: add a one-line inline callout the first time each glyph appears, or a compact legend in the page's own hero copy.
  **Suggested command**: `/impeccable clarify`

#### Persona Red Flags

**Alex (Power User)**: No cancel/interrupt affordance is shown for an in-flight tool call. No bulk expand/collapse for a multi-call chain — the one example with three calls only supports toggling them individually, which won't scale to Alex's real ten-plus-call chains. The "/ commands" hint is static text with no visible autocomplete/palette behind it — Alex will type `/` expecting a real command list.

**Sam (Accessibility / Screen Reader)**: `ChatMessage` doesn't appear to supply an accessible turn-role label (e.g. a visually-hidden "You:"/"Assistant:") to replace what sighted users read from glyph + position. The `digichat — session` header is CSS-generated `content:` text on a `::before` pseudo-element — not real accessible text; `ChatTranscript` accepts an `aria-label` prop that could carry it, but the reference instance doesn't pass one. DESIGN.md itself documents that `--accent-digichat` fails to fall back to the AA-safe neutral teal on light theme (down to ~2.4:1) — since every identity mark on this page rides that accent, a light-theme low-vision visitor inherits a known, unfixed contrast bug across the whole surface. (Assessment B independently confirmed the status glyphs *do* carry distinct classes, not color alone — but noted, unverified, that the glyph `<span>` itself carries no `aria-label`/`sr-only` text, so assistive tech likely falls back to the Unicode character's default name rather than explicit "success"/"error" wording.)

**Riley (Stress Tester)**: The only failure case demonstrated is a recoverable auth error — a genuinely failed computation (crashed run, NaN metrics) is never modeled, so it's unclear whether the surface has a different visual grammar for "retry" versus "fix your token." No cascading-failure sequence is shown. A real long single-line output or 50+ line result block is never re-demonstrated, so a genuine stress case remains unverified on this specimen.

#### Minor Observations

- The reference app's own "Page livery" selector defaults to displaying "monochrome" on this exact page even though the chatbot page is independently scoped to the digichat rose via a className — a visitor checking the dropdown for "what accent am I looking at" gets a mismatched answer.
- `--surface-inverse` is used with a hardcoded fallback (`#06110f`) in the composer send button, `.cw-btn--primary`, and `controls-core.css` rather than being a declared token — DESIGN.md already names this as a bug to fix, not a pattern to imitate elsewhere.
- The metrics grid's `max-[560px]:grid-cols-2` proves the team already has a working mobile-accommodation pattern on this same page — which makes its absence on the composer tray and the site header read as an oversight, not a constraint.
- Detector's directory scope (chatbot-only) missed the real defects, which live in shared/site-wide files (`site-nav.tsx`, `globals.css`) — worth widening the detector's scan surface for future runs of this command.

#### Questions to Consider

- If the single biggest anxiety moment for this audience is "is my 8-year backtest still running or stuck," why does the reference never show a live/running tool call at rest — shouldn't the specimen prove out the one state its own premise depends on?
- The page's strongest emotional beat (the human-approval gate) lands last — is that deliberate peak-end sequencing, or would adding an 8th demo section after it quietly undo the best closing note the page has?
- `--accent-digichat` is documented as failing contrast in light theme, and this entire surface's identity *is* that accent — has anyone actually looked at this page in light mode recently?
- The composer enforces a hard 2000-character cap with a live counter — is that a considered limit for real prompts (which might include pasted configs or multi-parameter backtest specs), or a demo constant nobody has revisited?
