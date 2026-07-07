"use client";

import { useState } from "react";

export function FormFieldsReference() {
  const [checks, setChecks] = useState({ audit: true, paper: false });
  const [mode, setMode] = useState("paper");
  const [motion, setMotion] = useState(true);

  return (
    <section className="section-block">
      <p className="kicker">{"// form fields"}</p>
      <h2 className="title">Every field, every state.</h2>
      <p className="section-copy">
        Labelled inputs in mono micro-caps: focus lights the accent ring, error swaps the border to
        <code> --down</code> with a message beneath, disabled dims and locks. Below, the selection
        controls — checkbox, radio group, and a toggle — each keyboard-reachable.
      </p>

      <div className="ff-grid">
        <label className="ff-field">
          <span className="ff-label">Email</span>
          <input className="ff-input" type="email" placeholder="you@desk.tld" defaultValue="" />
          <span className="ff-help">Used for audit notifications only.</span>
        </label>

        <label className="ff-field">
          <span className="ff-label">Strategy name</span>
          <input className="ff-input" type="text" defaultValue="trend_xsec" />
          <span className="ff-help">Lowercase, snake_case.</span>
        </label>

        <label className="ff-field is-error">
          <span className="ff-label">API key</span>
          <input className="ff-input" type="text" defaultValue="dk_live_9f2…" aria-invalid="true" />
          <span className="ff-err">Key is revoked — issue a new one.</span>
        </label>

        <label className="ff-field is-disabled">
          <span className="ff-label">Region</span>
          <input className="ff-input" type="text" value="us-east-1" disabled readOnly />
          <span className="ff-help">Locked to your workspace.</span>
        </label>

        <label className="ff-field ff-field--wide">
          <span className="ff-label">Notes</span>
          <textarea className="ff-input ff-textarea" rows={3} defaultValue="" placeholder="What is this run testing?" />
        </label>
      </div>

      <div className="ff-controls">
        <div className="ff-ctl-group">
          <p className="ctl-sub">checkbox</p>
          {[
            { k: "audit", label: "Audit logging" },
            { k: "paper", label: "Paper trading" },
          ].map((c) => (
            <label key={c.k} className="ff-check">
              <input
                type="checkbox"
                checked={checks[c.k as keyof typeof checks]}
                onChange={(e) => setChecks((s) => ({ ...s, [c.k]: e.target.checked }))}
              />
              <span className="ff-box" aria-hidden="true" />
              <span>{c.label}</span>
            </label>
          ))}
        </div>

        <div className="ff-ctl-group">
          <p className="ctl-sub">radio · execution mode</p>
          {["backtest", "paper", "live"].map((m) => (
            <label key={m} className="ff-radio">
              <input type="radio" name="ff-mode" checked={mode === m} onChange={() => setMode(m)} />
              <span className="ff-dot" aria-hidden="true" />
              <span>{m}</span>
            </label>
          ))}
        </div>

        <div className="ff-ctl-group">
          <p className="ctl-sub">toggle</p>
          <label className="ff-toggle-row">
            <button
              type="button"
              role="switch"
              aria-checked={motion}
              className={`ff-toggle${motion ? " on" : ""}`}
              onClick={() => setMotion((v) => !v)}
            >
              <span className="ff-knob" aria-hidden="true" />
            </button>
            <span>Reduced-motion respect</span>
          </label>
        </div>
      </div>
    </section>
  );
}
