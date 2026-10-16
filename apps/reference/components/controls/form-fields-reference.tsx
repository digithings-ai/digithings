"use client";

import { useState } from "react";

import {
  Checkbox,
  Form,
  FormActions,
  FormField,
  Input,
  Label,
  Radio,
  RadioGroup,
  Switch,
  Textarea,
} from "@digithings/ui/ui";

/**
 * Form fields — labelled inputs in mono micro-caps across every state: focus
 * lights the accent ring, error swaps the border to the danger tone with a
 * message beneath, disabled dims and locks. Below sit the selection controls —
 * checkbox, radio group, and a toggle — each keyboard-reachable.
 *
 * Wave 1: the fields are the stock kit — Input/Textarea/Label from
 * `@digithings/ui/ui`, error via the input's own `aria-invalid` treatment,
 * disabled via `disabled`. The mono micro-caps label type is the reference's
 * call-site grammar (the same utilities the native labels carried before).
 * Wave 4: Checkbox and Switch are the stock kit too (`@digithings/ui/ui`,
 * Base UI).
 * Batch K2: the hand-rolled label + input + hint grid is now the kit's
 * `Form` / `FormField` / `FormActions` presentational wrapper (no form
 * library — the repo has none). Radio/RadioGroup stay on the controls layer
 * until a later batch.
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

      <Form className="mt-[1.2rem] grid-cols-2 max-[640px]:grid-cols-1">
        <FormField label="Email" hint="Used for audit notifications only.">
          <Input
            name="email"
            type="email"
            autoComplete="email"
            placeholder="you@desk.tld"
          />
        </FormField>

        <FormField label="Strategy name" hint="Lowercase, snake_case.">
          <Input
            name="strategy"
            type="text"
            autoComplete="off"
            defaultValue="trend_xsec"
          />
        </FormField>

        <FormField label="API key" error="Key is revoked — issue a new one.">
          <Input
            name="api-key"
            type="text"
            autoComplete="off"
            defaultValue="dk_live_9f2…"
          />
        </FormField>

        <FormField label="Region" hint="Locked to your workspace.">
          <Input name="region" type="text" autoComplete="off" value="us-east-1" disabled readOnly />
        </FormField>

        <div className="col-span-full">
          <FormField label="Notes">
            <Textarea name="notes" rows={3} placeholder="What is this run testing?" />
          </FormField>
        </div>

        <FormActions className="col-span-full">
          <span className="font-mono text-[0.62rem] text-ink-mute">
            No submit — the canon is a static display template.
          </span>
        </FormActions>
      </Form>

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
