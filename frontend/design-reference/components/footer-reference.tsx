"use client";

import { useState } from "react";

const COLUMNS = [
  { title: "Product", links: ["DigiGraph", "DigiQuant", "DigiSearch", "DigiChat"] },
  { title: "Company", links: ["About", "Careers", "Blog"] },
  { title: "Resources", links: ["Docs", "Changelog", "Status"] },
  { title: "Connect", links: ["GitHub", "Discord", "X"] },
];

const THEMES = ["System", "Light", "Dark"] as const;

export function FooterReference() {
  const [theme, setTheme] = useState<(typeof THEMES)[number]>("System");

  return (
    <section className="section-block footer-ref">
      <p className="kicker">{"// footer & chrome"}</p>
      <h2 className="title">Utility rows, one personality moment.</h2>
      <p className="section-copy">
        The footer is the one sanctioned zone for color play — a single ambient bloom under the
        wordmark, quarantined from the rest of the flat chrome above it. Everywhere else stays
        hairline.
      </p>

      <footer className="ref-footer">
        <div className="ref-footer-columns">
          {COLUMNS.map((col) => (
            <div key={col.title}>
              <p className="ref-footer-col-title">{col.title}</p>
              <ul>
                {col.links.map((link) => (
                  <li key={link}>{link}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="ref-footer-utility">
          <span className="ref-footer-status">
            <span className="status-dot" aria-hidden="true" />
            All systems operational
          </span>

          <span className="ref-footer-theme" role="group" aria-label="Theme">
            {THEMES.map((option) => (
              <button
                key={option}
                type="button"
                className={option === theme ? "on" : ""}
                onClick={() => setTheme(option)}
                aria-pressed={option === theme}
              >
                {option}
              </button>
            ))}
          </span>

          <span className="ref-footer-copyright">© 2026 DigiThings · SOC 2 in progress</span>
        </div>

        <div className="ref-footer-brand">
          <span className="ref-footer-bloom" aria-hidden="true" />
          <span className="ref-footer-mark">
            digi<em>things</em>
          </span>
        </div>
      </footer>
    </section>
  );
}
