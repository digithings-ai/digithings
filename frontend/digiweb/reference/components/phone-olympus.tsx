import { OlympusMark } from "@/components/symbols/marks";

/**
 * Phone mockup showcasing the olympus app — a device frame (matte bezel,
 * dynamic-island, side buttons) wrapping a mock olympus mobile dashboard.
 * Product-surface grammar like MockTearsheet: an inline SVG sparkline, no
 * charting engine. Money colors (--up/--down) stay on P&L reads; the accent
 * dresses chrome and re-themes with the livery; sub-graph names are lowercase.
 */
const SIGNALS = [
  { scope: "atlas", name: "trend_xsec", pct: "+2.31%", up: true },
  { scope: "hermes", name: "carry", pct: "+0.94%", up: true },
  { scope: "atlas", name: "pairs", pct: "−0.62%", up: false },
];

export function PhoneOlympus() {
  return (
    <div className="phone" role="img" aria-label="olympus mobile app mockup">
      <span className="phone-btn phone-btn--power" aria-hidden="true" />
      <span className="phone-btn phone-btn--vol" aria-hidden="true" />
      <div className="phone-screen">
        <div className="phone-island" aria-hidden="true" />

        <div className="oly-status" aria-hidden="true">
          <span>9:41</span>
          <span className="oly-status-r">
            <i />
            <i />
            <i />
          </span>
        </div>

        <header className="oly-head">
          <span className="oly-brand">
            <OlympusMark size={18} />
            olympus
          </span>
          <span className="oly-live">
            <span className="oly-live-dot" aria-hidden="true" />
            live
          </span>
        </header>

        <div className="oly-hero">
          <span className="oly-hero-label">portfolio</span>
          <span className="oly-hero-value">$1.284M</span>
          <span className="oly-hero-delta up">+$5.47K · +0.43% today</span>
        </div>

        <div className="oly-chart" aria-hidden="true">
          <svg viewBox="0 0 280 96" preserveAspectRatio="none">
            <defs>
              <linearGradient id="olyfill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="currentColor" stopOpacity="0.28" />
                <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path
              d="M0 74 L28 68 56 72 84 52 112 58 140 40 168 46 196 26 224 32 252 16 280 22 L280 96 L0 96 Z"
              fill="url(#olyfill)"
            />
            <polyline
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinejoin="round"
              points="0,74 28,68 56,72 84,52 112,58 140,40 168,46 196,26 224,32 252,16 280,22"
            />
          </svg>
        </div>

        <p className="oly-section">signals</p>
        <ul className="oly-list">
          {SIGNALS.map((s) => (
            <li key={`${s.scope}-${s.name}`} className="oly-row">
              <span className="oly-scope">{s.scope}</span>
              <span className="oly-name">{s.name}</span>
              <span className={`oly-pct ${s.up ? "up" : "down"}`}>{s.pct}</span>
            </li>
          ))}
        </ul>

        <nav className="oly-tabs" aria-hidden="true">
          {[
            "M4 11 12 4l8 7M6 10v9h12v-9",
            "M4 19V5M9 19v-8M14 19V9M19 19v-5",
            "M4 6h16M4 12h16M4 18h10",
            "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6M19 12l1.5-1-1-2-1.8.4a6 6 0 0 0-1.6-.9L15 6H9l-.6 2.6a6 6 0 0 0-1.6.9L5 9.1l-1 2L5.5 12 4 13l1 2 1.8-.4a6 6 0 0 0 1.6.9L9 18h6l.6-2.6a6 6 0 0 0 1.6-.9l1.8.4 1-2z",
          ].map((d, i) => (
            <span key={d} className={`oly-tab${i === 0 ? " on" : ""}`}>
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d={d} />
              </svg>
            </span>
          ))}
        </nav>
      </div>
    </div>
  );
}
