"use client";

import { StackLogo } from "@digithings/ui";
import {
  OWNED_COMPONENTS,
  RENTED_BILLS,
  RENTED_COMPONENTS,
  SEAM_LABELS,
  SLOTS,
  type StackComponent,
} from "@/lib/whyStack";

/**
 * The two architecture views (round 9, #4429).
 *
 * ONE grammar, drawn twice. The owner: "the two visuals … should be somewhat
 * similar, just changing the components and the wiring to a certain degree …
 * it could be an actual architecture visualization of how true designers and
 * software developers would architect the platform … And most importantly, the
 * cost, everything cost, cost, cost, cost, cost, and then you end up with a
 * massive bill."
 *
 * So both views are HTML/CSS (not SVG) for two reasons: the vendor marks are the
 * kit's `StackLogo` component and cannot be nested inside an `<svg>`, and the
 * owner asked for the terminal look — "utilitarian, terminal-like … squared
 * edges and simplicity … It's a bit too modern" — which is hairlines, mono type
 * and `border-radius: 0`, not drawn shapes.
 *
 * Both views have the same anatomy, so the eye can diff them:
 *   - a left rail of the five slots, top to bottom, in the same order;
 *   - one or more boxes per slot, each a named thing with its icon and its
 *     billing cadence;
 *   - a vertical bus the slot rail hangs off, and a stub from each slot out to
 *     the ledger on the right;
 *   - a ledger column: on the rented side that is one invoice per box (which is
 *     how the bill becomes "massive" — by count, not by an invented number); on
 *     the owned side it is the single line "your provider accounts".
 *
 * The rented view also carries the SURFACE rule — the owner's "it's mostly just
 * surface layer, you get the end products, you don't get to customize anything
 * behind that, or create your own apps". Everything below the rule is marked as
 * somebody else's.
 *
 * HONESTY: no amount, percentage or "Nx cheaper" appears anywhere. Every box
 * states how the thing bills, which is public, and the ledger counts invoices.
 */

const seamFor = (slot: string): string | null =>
  SEAM_LABELS.find((entry) => entry.id === slot)?.seam ?? null;

const boxesFor = (components: StackComponent[], slot: string): StackComponent[] =>
  components.filter((component) => component.slot === slot);

/** One box: the mark, the name, the cadence. Lit boxes are the current step's. */
function Box({ component, lit }: { component: StackComponent; lit: boolean }) {
  return (
    <div className="whyx-box" data-lit={lit ? "true" : "false"}>
      <span className="whyx-box__mark">
        <StackLogo item={{ name: component.name, icon: component.icon }} />
      </span>
      <span className="whyx-box__cadence">{component.cadence}</span>
    </div>
  );
}

/** The slot rail — identical in both views. */
function SlotRail({
  components,
  lit,
  seams,
}: {
  components: StackComponent[];
  lit: string[];
  seams: boolean;
}) {
  return (
    <ol className="whyx-slots">
      {SLOTS.map((slot) => (
        <li key={slot.id} className="whyx-slot" data-slot={slot.id}>
          <span className="whyx-slot__name">{slot.layer}</span>
          <div className="whyx-slot__boxes">
            {boxesFor(components, slot.id).map((component) => (
              <Box key={component.name} component={component} lit={lit.includes(component.name)} />
            ))}
          </div>
          <span className="whyx-slot__seam">
            {seams ? seamFor(slot.id) : "their interface, their terms"}
          </span>
        </li>
      ))}
    </ol>
  );
}

/**
 * The rented stack. The ledger grows one invoice per box as the steps advance.
 */
export function RentedStack({ lit }: { lit: string[] }) {
  const billed = RENTED_COMPONENTS.filter((component) => lit.includes(component.name));
  return (
    <div className="whyx-view" data-side="rented">
      <div className="whyx-view__arch">
        <div className="whyx-bus" aria-hidden="true" />
        <SlotRail components={RENTED_COMPONENTS} lit={lit} seams={false} />
        <p className="whyx-surface">
          <span className="whyx-surface__rule" aria-hidden="true" />
          the surface — everything below this line is somebody else&rsquo;s
        </p>
      </div>
      <div className="whyx-ledger" aria-label="Invoices for the rented stack">
        <p className="whyx-ledger__head">
          <span>invoices</span>
          <span className="whyx-ledger__count">
            {billed.length}/{RENTED_BILLS}
          </span>
        </p>
        <ul className="whyx-ledger__list">
          {billed.map((component) => (
            <li key={component.name} className="whyx-ledger__line">
              <span className="whyx-ledger__vendor">{component.name}</span>
              <span className="whyx-ledger__cadence">{component.cadence}</span>
            </li>
          ))}
        </ul>
        <p className="whyx-ledger__foot">
          one meter per box · nothing consolidates · nothing above the surface line is yours to
          change
        </p>
      </div>
    </div>
  );
}

/** The owned stack. The same anatomy; the ledger is your own accounts. */
export function OwnedStack({ lit }: { lit: string[] }) {
  return (
    <div className="whyx-view" data-side="owned">
      <div className="whyx-view__arch">
        <div className="whyx-bus" aria-hidden="true" />
        <SlotRail components={OWNED_COMPONENTS} lit={lit} seams />
        <p className="whyx-surface whyx-surface--owned">
          <span className="whyx-surface__rule" aria-hidden="true" />
          no surface to break through — the seams are the product
        </p>
      </div>
      <div className="whyx-ledger" aria-label="Accounts for the owned stack">
        <p className="whyx-ledger__head">
          <span>accounts</span>
          <span className="whyx-ledger__count">yours</span>
        </p>
        <ul className="whyx-ledger__list">
          <li className="whyx-ledger__line">
            <span className="whyx-ledger__vendor">your provider accounts</span>
            <span className="whyx-ledger__cadence">you already pay them directly</span>
          </li>
        </ul>
        <p className="whyx-ledger__foot">
          no meter in the middle · each layer scales where it already runs · you ship the app
        </p>
      </div>
    </div>
  );
}
