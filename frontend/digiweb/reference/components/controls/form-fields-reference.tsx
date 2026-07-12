"use client";

import { useState } from "react";

/**
 * Form fields — labelled inputs in mono micro-caps across every state: focus
 * lights the accent ring, error swaps the border to --down with a message
 * beneath, disabled dims and locks. Below sit the selection controls — checkbox,
 * radio group, and a toggle — each keyboard-reachable and driven from the native
 * input's :checked. Static interactive display template.
 */
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

      <div className="mt-[1.2rem] grid grid-cols-2 gap-[1rem] max-[640px]:grid-cols-1">
        <label className="ff-field flex flex-col gap-[0.35rem]">
          <span className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">Email</span>
          <input className="ff-input" type="email" placeholder="you@desk.tld" defaultValue="" />
          <span className="font-mono text-[0.62rem] text-ink-mute">Used for audit notifications only.</span>
        </label>

        <label className="ff-field flex flex-col gap-[0.35rem]">
          <span className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">Strategy name</span>
          <input className="ff-input" type="text" defaultValue="trend_xsec" />
          <span className="font-mono text-[0.62rem] text-ink-mute">Lowercase, snake_case.</span>
        </label>

        <label className="ff-field is-error flex flex-col gap-[0.35rem]">
          <span className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">API key</span>
          <input className="ff-input" type="text" defaultValue="dk_live_9f2…" aria-invalid="true" />
          <span className="font-mono text-[0.62rem] text-down">Key is revoked — issue a new one.</span>
        </label>

        <label className="ff-field is-disabled flex flex-col gap-[0.35rem]">
          <span className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">Region</span>
          <input className="ff-input" type="text" value="us-east-1" disabled readOnly />
          <span className="font-mono text-[0.62rem] text-ink-mute">Locked to your workspace.</span>
        </label>

        <label className="ff-field col-span-full flex flex-col gap-[0.35rem]">
          <span className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">Notes</span>
          <textarea className="ff-input ff-textarea" rows={3} defaultValue="" placeholder="What is this run testing?" />
        </label>
      </div>

      <div className="mt-[1.6rem] flex flex-wrap gap-[2rem]">
        <div className="flex flex-col gap-[0.5rem]">
          <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            checkbox
          </p>
          {[
            { k: "audit", label: "Audit logging" },
            { k: "paper", label: "Paper trading" },
          ].map((c) => (
            <label
              key={c.k}
              className="ff-check flex cursor-pointer items-center gap-[0.55rem] font-mono text-[0.8rem] text-ink-soft"
            >
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

        <div className="flex flex-col gap-[0.5rem]">
          <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            radio · execution mode
          </p>
          {["backtest", "paper", "live"].map((m) => (
            <label
              key={m}
              className="ff-radio flex cursor-pointer items-center gap-[0.55rem] font-mono text-[0.8rem] text-ink-soft"
            >
              <input type="radio" name="ff-mode" checked={mode === m} onChange={() => setMode(m)} />
              <span className="ff-dot" aria-hidden="true" />
              <span>{m}</span>
            </label>
          ))}
        </div>

        <div className="flex flex-col gap-[0.5rem]">
          <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            toggle
          </p>
          <label className="flex cursor-pointer items-center gap-[0.55rem] font-mono text-[0.8rem] text-ink-soft">
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
