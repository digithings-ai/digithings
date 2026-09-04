/**
 * Slider — the shared parameter control, promoted from the reference slider
 * specimen. Deliberately a skinned NATIVE <input type="range"> (not a base-ui
 * composite): keyboard travel, tick semantics, and screen-reader value
 * narration come free, and the track fill is a computed gradient so it
 * aligns exactly. The input itself wears the shared `.ctl-slider-input`
 * mechanic (square thumb, sharp-corner grammar); this composite adds the
 * label row, live mono readout, optional ticks, and disabled wash. All dress
 * lives in styles/controls-core.css (`.ctl-slider*`, import once app-wide);
 * this file carries no Tailwind utilities, so no `@source` line is needed
 * for it.
 */
import { useId } from "react";

import { cx } from "./cx";

export type SliderProps = Omit<
  React.ComponentProps<"input">,
  "type" | "value" | "defaultValue" | "onChange" | "children"
> & {
  label?: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange?: (value: number) => void;
  /** Readout formatter. Defaults to the raw value. */
  format?: (value: number) => string;
  ticks?: number[];
};

export function sliderFill(value: number, min: number, max: number): string {
  const pct = ((value - min) / (max - min)) * 100;
  return `linear-gradient(to right, var(--accent) 0 ${pct}%, color-mix(in srgb, var(--ink) 14%, transparent) ${pct}% 100%)`;
}

export function Slider({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  onChange,
  format = (v) => String(v),
  ticks,
  disabled = false,
  id,
  className,
  ...props
}: SliderProps) {
  const autoId = useId();
  const inputId = id ?? `${autoId}-slider`;
  const readoutId = `${autoId}-readout`;
  return (
    <div
      data-slot="slider"
      data-disabled={disabled ? true : undefined}
      className={cx("ctl-slider", disabled && "is-disabled", className)}
    >
      {label ? (
        <div className="ctl-slider-head">
          <label htmlFor={inputId} className="ctl-slider-label">
            {label}
          </label>
          <span id={readoutId} className="ctl-slider-value">
            {format(value)}
          </span>
        </div>
      ) : null}
      <input
        type="range"
        id={inputId}
        className="ctl-slider-input"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        style={{ background: sliderFill(value, min, max) }}
        aria-label={label == null ? "Value" : undefined}
        aria-describedby={label ? readoutId : undefined}
        onChange={(e) => onChange?.(Number(e.target.value))}
        {...props}
      />
      {ticks ? (
        <div className="ctl-slider-ticks" aria-hidden="true">
          {ticks.map((t) => (
            <span key={t}>{t}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
