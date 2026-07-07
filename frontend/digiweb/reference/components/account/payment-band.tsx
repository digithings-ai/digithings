"use client";

import type { FormEvent } from "react";

/**
 * Payment band — a checkout pairing: card form on the left, plan receipt on the
 * right. Every charge is a hairline row with a mono figure and only the total
 * spends full ink; the loading state reuses the house spinner button rather than
 * anything bespoke. An interactive display template.
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
          <div className="acct-field">
            <label
              className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
              htmlFor="pay-name"
            >
              Cardholder
            </label>
            <input
              className="acct-input"
              id="pay-name"
              name="cardholder"
              type="text"
              placeholder="C. Stefan"
              autoComplete="off"
            />
          </div>
          <div className="acct-field">
            <label
              className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
              htmlFor="pay-card"
            >
              Card number
            </label>
            <input
              className="acct-input"
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
            <div className="acct-field">
              <label
                className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="pay-expiry"
              >
                Expiry
              </label>
              <input
                className="acct-input"
                id="pay-expiry"
                name="expiry"
                type="text"
                inputMode="numeric"
                placeholder="MM / YY"
                maxLength={7}
                autoComplete="off"
              />
            </div>
            <div className="acct-field">
              <label
                className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="pay-cvc"
              >
                CVC
              </label>
              <input
                className="acct-input"
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
            <button type="submit" className="btn-primary">
              Pay $165.56
            </button>
            <button type="button" className="btn-primary btn-loading" disabled>
              <span className="btn-spinner" aria-hidden="true" />
              Processing…
            </button>
          </div>
        </form>

        <aside
          className="rounded-[12px] border border-hair bg-surface p-[1.1rem]"
          aria-label="Plan summary"
        >
          <div className="flex items-center justify-between gap-[0.8rem]">
            <p className="text-[0.95rem] text-ink">Desk plan</p>
            <span className="inline-block whitespace-nowrap rounded-full border border-hair px-[0.6rem] py-[0.22rem] font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
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
              <span>hermes add-on</span>
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
