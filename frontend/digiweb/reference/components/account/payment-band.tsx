"use client";

import type { FormEvent } from "react";

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

      <div className="acct-pay-band">
        <form className="acct-pay-form" onSubmit={preventSubmit} noValidate>
          <div className="acct-field">
            <label className="acct-label" htmlFor="pay-name">
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
            <label className="acct-label" htmlFor="pay-card">
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
          <div className="acct-pay-row">
            <div className="acct-field">
              <label className="acct-label" htmlFor="pay-expiry">
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
              <label className="acct-label" htmlFor="pay-cvc">
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
          <div className="acct-pay-actions">
            <button type="submit" className="btn-primary">
              Pay $165.56
            </button>
            <button type="button" className="btn-primary btn-loading" disabled>
              <span className="btn-spinner" aria-hidden="true" />
              Processing…
            </button>
          </div>
        </form>

        <aside className="acct-plan" aria-label="Plan summary">
          <div className="acct-plan-head">
            <p className="acct-plan-name">Desk plan</p>
            <span className="acct-badge">example data · not live</span>
          </div>
          <p className="acct-plan-price">$40 / seat / month</p>
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
          <p className="acct-plan-total">
            <span>due today</span>
            <span>$165.56</span>
          </p>
        </aside>
      </div>
    </section>
  );
}
