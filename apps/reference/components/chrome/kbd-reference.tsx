import { Kbd } from "@digithings/ui/ui";

/**
 * Keycap chip — the kit `Kbd`, promoted from this gallery's own global `.kbd`
 * class. That class was reference-only: an app that wanted a keycap had no
 * canonical part, so it would either re-implement one (tripping the family
 * census) or hand-copy the reference sheet. The promotion makes the keycap a
 * real part, rendered as a semantic `<kbd>`.
 */
export function KbdReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// keycap chip"}</p>
      <h2 className="title">Keycaps, owned by the kit.</h2>
      <p className="section-copy">
        <code>Kbd</code> renders a real <code>&lt;kbd&gt;</code> in the keycap dress — hairline
        box, heavier bottom edge, ink-wash fill, mono micro type. It takes single keys
        (<code>⌘</code>, <code>K</code>, <code>esc</code>) and multi-character codes (a phase id
        like <code>h7e</code>) without collapsing.
      </p>
      <div className="btn-row">
        <Kbd>⌘</Kbd>
        <Kbd>K</Kbd>
        <Kbd>esc</Kbd>
        <Kbd>↵</Kbd>
        <Kbd>h7e</Kbd>
        <Kbd>01</Kbd>
      </div>
    </section>
  );
}
