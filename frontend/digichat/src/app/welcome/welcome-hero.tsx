/**
 * Frozen "product screenshot" of the DigiChat terminal UI, for the /welcome
 * marketing hero (#1218). Reuses the live `app-shell` / `dc-sidebar-*` /
 * `dc-term-*` classes (defined in globals.css) so it reads as the real product,
 * but every value is hardcoded — NO hooks, session, or fetch. `ChatShell`/
 * `ChatPanel` can't be imported here (they require a live session). Cyan accent
 * comes free from `.app-shell { --accent: #3dd6c4 }`. Decorative → aria-hidden;
 * the bounded `.welcome-hero-frame` (welcome.css) crops it to a screenshot.
 */
export function WelcomeHero() {
  return (
    <div className="welcome-hero-frame" aria-hidden="true">
      <div className="app-shell">
        <aside className="app-sidebar" data-expanded="true">
          <div className="app-sidebar-body">
            <div className="dc-sidebar-brand">
              <div className="dc-sidebar-brand-mark">DT</div>
              <div>
                <div className="dc-sidebar-brand-name">DigiChat</div>
                <div className="dc-sidebar-brand-version">v0.1 · digithings</div>
              </div>
            </div>
            <button type="button" className="dc-sidebar-newchat" tabIndex={-1}>
              + New chat
            </button>
            <section className="app-sidebar-section">
              <div className="dc-sidebar-thread" role="button" aria-pressed="true">
                <span className="dc-sidebar-thread-title">Q3 filings digest</span>
                <span className="dc-sidebar-thread-time">now</span>
              </div>
              <div className="dc-sidebar-thread" role="button" aria-pressed="false">
                <span className="dc-sidebar-thread-title">FX regime check</span>
                <span className="dc-sidebar-thread-time">2h</span>
              </div>
              <div className="dc-sidebar-thread" role="button" aria-pressed="false">
                <span className="dc-sidebar-thread-title">Backtest: BTC slapper</span>
                <span className="dc-sidebar-thread-time">1d</span>
              </div>
            </section>
            <section className="app-sidebar-section">
              <ul>
                <li className="dc-sidebar-cmd">
                  <span className="dc-sidebar-cmd-key">/help</span>
                </li>
                <li className="dc-sidebar-cmd">
                  <span className="dc-sidebar-cmd-key">/model</span>
                </li>
                <li className="dc-sidebar-cmd">
                  <span className="dc-sidebar-cmd-key">/clear</span>
                </li>
              </ul>
            </section>
          </div>
        </aside>

        <div className="app-shell-main-col">
          <header className="app-topbar">
            <span className="app-topbar-title">Q3 filings digest</span>
            <span className="app-topbar-meta">claude-sonnet-5 · BYOK · audit-on</span>
          </header>
          <main className="app-main">
            <div className="dc-term-pane">
              <div className="dc-term-row dc-term-row-user">
                <span className="dc-term-marker">$</span>
                <div className="dc-term-body">
                  Summarize the risk factors across today&apos;s 10-Q filings.
                </div>
              </div>
              <div className="dc-term-row dc-term-row-assistant">
                <span className="dc-term-marker">▸</span>
                <div className="dc-term-body">
                  Three themes dominate: FX exposure on non-USD revenue, tightening liquidity
                  guidance, and one supply-chain concentration flag. Sources linked per claim.
                </div>
              </div>
              <div className="dc-term-row dc-term-row-assistant">
                <span className="dc-term-marker">·</span>
                <div className="dc-term-body" style={{ color: "var(--text-secondary)" }}>
                  digisearch · 12 passages retrieved · correlation id logged
                </div>
              </div>
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
