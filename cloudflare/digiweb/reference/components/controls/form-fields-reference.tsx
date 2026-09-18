"use client";

import { useState } from "react";

import { Radio, RadioGroup } from "@digithings/web";
import { Checkbox, Input, Label, Switch, Textarea } from "@digithings/web/ui";

/**
 * Form fields — labelled inputs in mono micro-caps across every state: focus
 * lights the accent ring, error swaps the border to the danger tone with a
 * message beneath, disabled dims and locks. Below sit the selection controls —
 * checkbox, radio group, and a toggle — each keyboard-reachable.
 *
 * Wave 1: the fields are the stock kit — Input/Textarea/Label from
 * `@digithings/web/ui`, error via the input's own `aria-invalid` treatment,
 * disabled via `disabled`, labels paired with `id`/`htmlFor`. The mono
 * micro-caps label type is the reference's call-site grammar (the same
 * utilities the native labels carried before); the `.ff-*` dress is gone.
 * Wave 4: Checkbox and Switch are the stock kit too (`@digithings/web/ui`,
 * Base UI). Radio/RadioGroup stay on the `@digithings/web` controls layer —
 * the kit has no radio part.
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
          <code> --danger</code> with a message beneath, disabled dims and locks. Below, the selection
          controls — checkbox, radio group, and a toggle — each keyboard-reachable.
        </p>

      <div className="mt-[1.2rem] grid grid-cols-2 gap-[1rem] max-[640px]:grid-cols-1">
        <div className="flex flex-col gap-[0.35rem]">
          <Label
            htmlFor="form-email"
            className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute"
          >
            Email
          </Label>
          <Input
            id="form-email"
            name="email"
            type="email"
            autoComplete="email"
            placeholder="you@desk.tld"
          />
          <span className="font-mono text-[0.62rem] text-ink-mute">Used for audit notifications only.</span>
        </div>

        <div className="flex flex-col gap-[0.35rem]">
          <Label
            htmlFor="form-strategy"
            className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute"
          >
            Strategy name
          </Label>
          <Input
            id="form-strategy"
            name="strategy"
            type="text"
            autoComplete="off"
            defaultValue="trend_xsec"
          />
          <span className="font-mono text-[0.62rem] text-ink-mute">Lowercase, snake_case.</span>
        </div>

        <div className="flex flex-col gap-[0.35rem]">
          <Label
            htmlFor="form-api-key"
            className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute"
          >
            API key
          </Label>
          <Input
            id="form-api-key"
            name="api-key"
            type="text"
            autoComplete="off"
            defaultValue="dk_live_9f2…"
            aria-invalid="true"
          />
          <span className="font-mono text-[0.62rem] text-danger">Key is revoked — issue a new one.</span>
        </div>

        <div className="flex flex-col gap-[0.35rem]">
          <Label
            htmlFor="form-region"
            className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute"
          >
            Region
          </Label>
          <Input
            id="form-region"
            name="region"
            type="text"
            autoComplete="off"
            value="us-east-1"
            disabled
            readOnly
          />
          <span className="font-mono text-[0.62rem] text-ink-mute">Locked to your workspace.</span>
        </div>

        <div className="col-span-full flex flex-col gap-[0.35rem]">
          <Label
            htmlFor="form-notes"
            className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute"
          >
            Notes
          </Label>
          <Textarea
            id="form-notes"
            name="notes"
            rows={3}
            placeholder="What is this run testing?"
          />
        </div>
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
            <Label
              key={c.k}
              htmlFor={`check-${c.k}`}
              className="flex cursor-pointer items-center gap-[0.55rem] font-mono text-[0.8rem] text-ink-soft"
            >
              <Checkbox
                id={`check-${c.k}`}
                name={c.k}
                checked={checks[c.k as keyof typeof checks]}
                onCheckedChange={(checked) => setChecks((s) => ({ ...s, [c.k]: checked }))}
              />
              <span>{c.label}</span>
            </Label>
          ))}
        </div>

        <div className="flex flex-col gap-[0.5rem]">
          <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            radio · execution mode
          </p>
          <RadioGroup
            name="execution-mode"
            value={mode}
            onValueChange={(value) => setMode(String(value))}
            className="flex flex-col gap-[0.5rem]"
          >
            {["backtest", "paper", "live"].map((m) => (
              <Label
                key={m}
                htmlFor={`mode-${m}`}
                className="flex cursor-pointer items-center gap-[0.55rem] font-mono text-[0.8rem] text-ink-soft"
              >
                <Radio id={`mode-${m}`} value={m} />
                <span>{m}</span>
              </Label>
            ))}
          </RadioGroup>
        </div>

        <div className="flex flex-col gap-[0.5rem]">
          <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            toggle
          </p>
          <Label
            htmlFor="form-motion"
            className="flex cursor-pointer items-center gap-[0.55rem] font-mono text-[0.8rem] text-ink-soft"
          >
            <Switch
              id="form-motion"
              name="motion"
              checked={motion}
              onCheckedChange={setMotion}
              aria-label="Reduced-motion respect"
            />
            <span aria-hidden="true">Reduced-motion respect</span>
          </Label>
        </div>
      </div>
    </section>
  );
}
