"use client";

import { useState } from "react";

/**
 * Settings — every preference stacked in one card: label and consequence on the
 * left, control (toggle, segmented switch, or select) on the right, a hairline
 * between each decision. The danger zone sits last behind one more hairline, the
 * only place red is spent. An interactive display template.
 */

type Theme = "system" | "light" | "dark";

const THEMES: { value: Theme; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

type ToggleProps = {
  on: boolean;
  labelledBy: string;
  onToggle: () => void;
};

function Toggle({ on, labelledBy, onToggle }: ToggleProps) {
  return (
    <button
      type="button"
      className="acct-toggle"
      aria-pressed={on}
      aria-labelledby={labelledBy}
      onClick={onToggle}
    >
      <span className="acct-toggle-knob" aria-hidden="true" />
    </button>
  );
}

export function SettingsPanel() {
  const [digests, setDigests] = useState(true);
  const [telemetry, setTelemetry] = useState(false);
  const [theme, setTheme] = useState<Theme>("system");

  return (
    <section className="section-block">
      <p className="kicker">{"// settings"}</p>
      <h2 className="title">Every switch in one column.</h2>
      <p className="section-copy">
        Grouped rows inside a single card: label and consequence on the left, control on the right,
        a hairline between each decision. The danger zone sits at the bottom behind one more
        hairline — red is reserved for it.
      </p>

      <div className="mt-[1.2rem] rounded-[12px] border border-hair bg-surface">
        <div className="acct-setting-row">
          <div>
            <p className="block text-[0.88rem] text-ink" id="setting-digests">
              Email digests
            </p>
            <p className="acct-setting-desc">Weekly PnL and drift summary, Mondays 07:00.</p>
          </div>
          <Toggle
            on={digests}
            labelledBy="setting-digests"
            onToggle={() => setDigests((value) => !value)}
          />
        </div>

        <div className="acct-setting-row">
          <div>
            <p className="block text-[0.88rem] text-ink" id="setting-telemetry">
              Usage telemetry
            </p>
            <p className="acct-setting-desc">Anonymous counters only — never strategy payloads.</p>
          </div>
          <Toggle
            on={telemetry}
            labelledBy="setting-telemetry"
            onToggle={() => setTelemetry((value) => !value)}
          />
        </div>

        <div className="acct-setting-row">
          <div>
            <p className="block text-[0.88rem] text-ink" id="setting-theme">
              Theme
            </p>
            <p className="acct-setting-desc">Follows the OS unless pinned.</p>
          </div>
          <div className="acct-segment" role="group" aria-labelledby="setting-theme">
            {THEMES.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={theme === option.value}
                onClick={() => setTheme(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="acct-setting-row">
          <div>
            <label className="block text-[0.88rem] text-ink" htmlFor="setting-module">
              Default module
            </label>
            <p className="acct-setting-desc">Where new sessions open.</p>
          </div>
          <span className="acct-select-wrap">
            <select className="acct-select" id="setting-module" defaultValue="digiquant">
              <option value="digiquant">digiquant</option>
              <option value="digigraph">digigraph</option>
              <option value="digisearch">digisearch</option>
              <option value="digivault">digivault</option>
            </select>
          </span>
        </div>

        <div className="acct-danger">
          <div>
            <p className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-down">danger zone</p>
            <p className="acct-setting-desc">
              Deletes every strategy, backtest, and API key in this workspace. No undo.
            </p>
          </div>
          <button type="button" className="btn-danger">
            Delete workspace
          </button>
        </div>
      </div>
    </section>
  );
}
