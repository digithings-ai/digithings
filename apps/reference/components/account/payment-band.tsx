"use client";

import type { FormEvent } from "react";

import { Spinner } from "@digithings/ui";
import { Button, Input, Label } from "@digithings/ui/ui";

/**
 * Payment band — a checkout pairing: card form on the left, plan receipt on the
 * right. Every charge is a hairline row with a mono figure and only the total
 * spends full ink; the loading state reuses the house spinner button rather than
 * anything bespoke. An interactive display template.
 *
 * Wave 1 / wave 3: card fields and both actions are the stock kit —
 * Input/Label/Button from `@digithings/ui/ui`; the block field spacing is
 * call-site grammar. The kit has no `loading` prop, so the processing state
 * is the wave-2 idiom: `disabled` plus the inline spinner span (same as
 * buttons-cta-reference). The old field dress is gone.
 */

function preventSubmit(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
}

export function PaymentBand() {
  return (
    <section className="section-block">
      <p className="kicker">{"// payment"}</p>
      <h2 className="title">Money math, shown line by line.</h2>
      <p className="section-copy">
        Form on the left, receipt on the right — every charge is a hairline row with a mono number,
        and the total is the only line allowed full ink. The loading state reuses the house spinner
        button, nothing bespoke.
      </p>

      <div className="mt-[1.2rem] grid grid-cols-[minmax(0,1fr)_320px] items-start gap-[1.2rem] max-[900px]:grid-cols-1">
        <form className="acct-pay-form" onSubmit={preventSubmit} noValidate>
          <div className="flex flex-col gap-[0.35rem]">
            <Label
              className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
              htmlFor="pay-name"
            >
              Cardholder
            </Label>
            <Input
              id="pay-name"
              name="cardholder"
              type="text"
              placeholder="C. Stefan"
              autoComplete="off"
            />
          </div>
          <div className="mt-[0.85rem] flex flex-col gap-[0.35rem]">
            <Label
              className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
              htmlFor="pay-card"
            >
              Card number
            </Label>
            <Input
              id="pay-card"
              name="card-number"
              type="text"
              inputMode="numeric"
              placeholder="4242 4242 4242 4242"
              maxLength={19}
              autoComplete="off"
            />
          </div>
          <div className="grid grid-cols-[repeat(2,minmax(0,1fr))] gap-[0.8rem]">
            <div className="flex flex-col gap-[0.35rem]">
              <Label
                className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="pay-expiry"
              >
                Expiry
              </Label>
              <Input
                id="pay-expiry"
                name="expiry"
                type="text"
                inputMode="numeric"
                placeholder="MM / YY"
                maxLength={7}
                autoComplete="off"
              />
            </div>
            <div className="flex flex-col gap-[0.35rem]">
              <Label
                className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="pay-cvc"
              >
                CVC
              </Label>
              <Input
                id="pay-cvc"
                name="cvc"
                type="text"
                inputMode="numeric"
                placeholder="···"
                maxLength={4}
                autoComplete="off"
              />
            </div>
          </div>
          <div className="mt-[1.2rem] flex flex-wrap items-center gap-[0.8rem]">
            <Button type="submit">Pay $165.56</Button>
            <Button type="button" disabled>
              <Spinner />
              Processing…
            </Button>
          </div>
        </form>

        <aside
          className="rounded-none border border-hair bg-surface p-[1.1rem]"
          aria-label="Plan summary"
        >
          <div className="flex items-center justify-between gap-[0.8rem]">
            <p className="text-[0.95rem] text-ink">Desk plan</p>
            <span className="inline-block whitespace-nowrap rounded-none border border-hair px-[0.6rem] py-[0.22rem] font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
              example data · not live
            </span>
          </div>
          <p className="mt-[0.3rem] font-mono text-[0.72rem] text-ink-mute">$40 / seat / month</p>
          <ul className="acct-plan-items">
            <li>
              <span>3 seats × $40</span>
              <span>$120.00</span>
            </li>
            <li>
              <span>portfolio add-on</span>
              <span>$24.00</span>
            </li>
            <li>
              <span>tax (14.975%)</span>
              <span>$21.56</span>
            </li>
          </ul>
          <p className="flex justify-between gap-4 border-t border-hair pt-[0.6rem] font-mono text-[0.8rem] text-ink">
            <span>due today</span>
            <span>$165.56</span>
          </p>
        </aside>
      </div>
    </section>
  );
}
