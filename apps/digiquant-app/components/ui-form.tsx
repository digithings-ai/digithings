'use client';

import { useId, useState, type InputHTMLAttributes, type ReactNode } from 'react';

/** Form primitives. Plain mono text; no boxes until focus. Labels always visible. */

export function Field({ label, hint, ...p }: { label: string; hint?: string } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <div className="fld">
      <label htmlFor={id} className="fld-l">{label}</label>
      <input id={id} className="fld-in" spellCheck={false} {...p} />
      {hint ? <span className="fld-h">{hint}</span> : null}
    </div>
  );
}

export function Select({ label, options, value, onChange, hint }: {
  label: string;
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="fld">
      <label htmlFor={id} className="fld-l">{label}</label>
      <select id={id} className="fld-in" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {hint ? <span className="fld-h">{hint}</span> : null}
    </div>
  );
}

/** On/off switch rendered as text: `[x] label` / `[ ] label`. */
export function Toggle({ label, on, onChange, hint }: { label: string; on: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <div className="fld">
      <button type="button" role="switch" aria-checked={on} className="tgl" onClick={() => onChange(!on)}>
        <span className="mono">[{on ? 'x' : ' '}]</span> {label}
      </button>
      {hint ? <span className="fld-h">{hint}</span> : null}
    </div>
  );
}

/** A secret is never rendered from data: only its tail. `reveal` is local and off by default. */
export function SecretField({ label, tail, hint }: { label: string; tail: string | null | undefined; hint?: string }) {
  const [show, setShow] = useState(false);
  const shown = tail ? (show ? `…${tail}` : `••••••••${tail}`) : '—';
  return (
    <div className="fld">
      <span className="fld-l">{label}</span>
      <span className="mono fld-v">
        {shown}
        {tail ? <> <button type="button" className="btn" onClick={() => setShow((s) => !s)}>{show ? 'hide' : 'show'}</button></> : null}
      </span>
      {hint ? <span className="fld-h">{hint}</span> : null}
    </div>
  );
}

/** Form row group: label column + body. */
export function FormRow({ children }: { children: ReactNode }) {
  return <div className="frow">{children}</div>;
}
