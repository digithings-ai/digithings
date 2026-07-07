"use client";

import { useState } from "react";

/**
 * Range sliders — the parameter control. A native <input type="range"> restyled
 * cross-browser: the track fills to the value with the accent (a computed
 * gradient, so it aligns exactly), a round thumb, a live mono readout, optional
 * tick marks, and a disabled state. Native means keyboard + a11y come free.
 * Accent fill reads under the monochrome default.
 */
function fill(value: number, min: number, max: number) {
  const pct = ((value - min) / (max - min)) * 100;
  return {
    background: `linear-gradient(to right, var(--accent) 0 ${pct}%, color-mix(in srgb, var(--ink) 14%, transparent) ${pct}% 100%)`,
  };
}

function Slider({
  label,
  min,
  max,
  step,
  value,
  onChange,
  format,
  ticks,
  disabled,
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange?: (v: number) => void;
  format: (v: number) => string;
  ticks?: number[];
  disabled?: boolean;
}) {
  return (
    <div className={`sl${disabled ? " sl--disabled" : ""}`}>
      <div className="sl-head">
        <span className="sl-label">{label}</span>
        <span className="sl-value">{format(value)}</span>
      </div>
      <input
        type="range"
        className="sl-input"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        style={fill(value, min, max)}
        aria-label={label}
        onChange={(e) => onChange?.(Number(e.target.value))}
      />
      {ticks ? (
        <div className="sl-ticks" aria-hidden="true">
          {ticks.map((t) => (
            <span key={t}>{format(t)}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function SliderReference() {
  const [kelly, setKelly] = useState(0.5);
  const [size, setSize] = useState(25);

  return (
    <section className="section-block">
      <p className="kicker">{"// slider"}</p>
      <h2 className="title">Dial the parameters.</h2>
      <p className="section-copy">
        A native range input restyled to the system: the track fills to the value in the accent,
        the thumb sits on top, and a mono readout tracks live. Arrow keys nudge, Home/End jump —
        all for free from the native control. Shown with tick marks and a locked state.
      </p>

      <div className="sl-grid">
        <Slider
          label="kelly cap"
          min={0}
          max={1}
          step={0.05}
          value={kelly}
          onChange={setKelly}
          format={(v) => `${v.toFixed(2)}×`}
        />
        <Slider
          label="max position"
          min={0}
          max={100}
          step={5}
          value={size}
          onChange={setSize}
          format={(v) => `${v}%`}
          ticks={[0, 25, 50, 75, 100]}
        />
        <Slider
          label="leverage (locked)"
          min={1}
          max={10}
          step={1}
          value={1}
          format={(v) => `${v}×`}
          disabled
        />
      </div>
    </section>
  );
}
