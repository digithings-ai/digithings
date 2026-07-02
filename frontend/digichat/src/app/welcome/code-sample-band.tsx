"use client";
/**
 * CodeSampleBand for the /welcome marketing route (#1218).
 *
 * A React port of the shared `.code-sample-band` primitive (the vanilla
 * `@digithings/design/code-sample-band.js` is not exported from the package and
 * this codebase prefers React state for interactive chrome — see #273). Markup
 * follows the WAI-ARIA tabs contract from the design-system README: a
 * `role="tablist"` owns only `role="tab"` buttons; the copy button is a sibling
 * in `__bar`, not inside the tablist. Styling + the `--term-*` tokens come from
 * the scoped `.welcome-codeband` wrapper in `welcome.css`.
 */
import { useState } from "react";
import { CODE_SAMPLES } from "@/lib/code-sample-band-data";

export function CodeSampleBand() {
  const [active, setActive] = useState(0);
  const [copied, setCopied] = useState(false);
  const sample = CODE_SAMPLES[active] ?? CODE_SAMPLES[0]!;

  async function copyActive() {
    try {
      await navigator.clipboard.writeText(sample.code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable (insecure context / denied) — no-op */
    }
  }

  return (
    <div className="welcome-codeband">
      <div className="code-sample-band">
        <div className="code-sample-band__bar">
          <div className="code-sample-band__tabs" role="tablist" aria-label="API usage examples">
            {CODE_SAMPLES.map((s, i) => (
              <button
                key={s.id}
                type="button"
                role="tab"
                id={`csb-tab-${s.id}`}
                aria-selected={i === active}
                aria-controls={`csb-panel-${s.id}`}
                tabIndex={i === active ? 0 : -1}
                className="code-sample-band__tab"
                onClick={() => setActive(i)}
              >
                {s.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            className={`code-sample-band__copy${copied ? " is-ok" : ""}`}
            aria-label="Copy code"
            onClick={copyActive}
          >
            {copied ? "copied" : "copy"}
          </button>
        </div>
        <pre
          className="code-sample-band__panel"
          role="tabpanel"
          id={`csb-panel-${sample.id}`}
          aria-labelledby={`csb-tab-${sample.id}`}
        >
          <code>{sample.code}</code>
        </pre>
      </div>
    </div>
  );
}
