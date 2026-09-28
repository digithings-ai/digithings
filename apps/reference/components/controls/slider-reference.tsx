"use client";

import { useState } from "react";

import { Slider } from "@digithings/ui/ui";

/**
 * Range sliders — the parameter control. Now the kit's Base UI `Slider`
 * (`@digithings/ui/ui`, #4306 batch K1): a 4px ink-tinted track, an accent
 * fill, and a square accent thumb. Single-thumb (`value={n}`) and range
 * (`value={[a, b]}`, one thumb per value) both work — the range row below is
 * the two-thumb proof the API claimed but the canon never showed.
 * `SliderRow`/`RangeSliderRow` are thin specimen scaffolds that add the label
 * row, live mono readout and optional ticks around the kit part — the old
 * hand-rolled native slider and its `.sl-input` mechanic are gone.
 */
function SliderRow({
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
    <div className={disabled ? "opacity-50" : undefined}>
      <div className="mb-[0.6rem] flex items-baseline justify-between">
        <span className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
          {label}
        </span>
        <span className="font-mono text-[0.86rem] tabular-nums text-ink">{format(value)}</span>
      </div>
      <Slider
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        aria-label={label}
        onValueChange={(v) => onChange?.(v as number)}
      />
      {ticks ? (
        <div
          className="mt-[0.55rem] flex justify-between font-mono text-[0.58rem] text-ink-mute"
          aria-hidden="true"
        >
          {ticks.map((t) => (
            <span key={t}>{format(t)}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Two-thumb range row — `value` is a `[min, max]` pair, so the kit resolves
 * two thumbs (one per value) and Base UI keeps them from crossing. The readout
 * joins the two ends with an en dash, matching the mono tabular grammar.
 */
function RangeSliderRow({
  label,
  min,
  max,
  step,
  value,
  onChange,
  format,
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: [number, number];
  onChange: (v: [number, number]) => void;
  format: (v: number) => string;
}) {
  return (
    <div>
      <div className="mb-[0.6rem] flex items-baseline justify-between">
        <span className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
          {label}
        </span>
        <span className="font-mono text-[0.86rem] tabular-nums text-ink">
          {format(value[0])} – {format(value[1])}
        </span>
      </div>
      <Slider
        value={value}
        min={min}
        max={max}
        step={step}
        aria-label={`${label} range`}
        onValueChange={(v) => onChange([...(v as number[])] as [number, number])}
      />
    </div>
  );
}

export function SliderReference() {
  const [kelly, setKelly] = useState(0.5);
  const [size, setSize] = useState(25);
  const [band, setBand] = useState<[number, number]>([20, 60]);

  return (
    <section className="section-block">
      <p className="kicker">{"// slider"}</p>
      <h2 className="title">Dial the parameters.</h2>
      <p className="section-copy">
        A Base UI slider restyled to the system: the track fills to the value in the accent,
        the thumb sits on top, and a mono readout tracks live. Arrow keys nudge, Home/End jump.
        Shown with tick marks, a locked state, and a two-thumb range — pass an array and the
        kit renders one thumb per value.
      </p>

      <div className="mt-[1.2rem] flex max-w-[30rem] flex-col gap-[1.6rem]">
        <SliderRow
          label="kelly cap"
          min={0}
          max={1}
          step={0.05}
          value={kelly}
          onChange={setKelly}
          format={(v) => `${v.toFixed(2)}×`}
        />
        <SliderRow
          label="max position"
          min={0}
          max={100}
          step={5}
          value={size}
          onChange={setSize}
          format={(v) => `${v}%`}
          ticks={[0, 25, 50, 75, 100]}
        />
        <RangeSliderRow
          label="confidence band"
          min={0}
          max={100}
          step={5}
          value={band}
          onChange={setBand}
          format={(v) => `${v}%`}
        />
        <SliderRow
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
