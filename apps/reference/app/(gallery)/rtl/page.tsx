import { RtlReference } from "@/components/rtl-reference";
import "./rtl.css";

export const metadata = {
  title: "RTL proof — digithings frontend design reference",
  description:
    "The canonical kit rendered LTR and dir=rtl: chrome, controls, overlays, tables and layouts.",
};

export default function RtlPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// foundations · rtl"}</p>
        <h1>
          The canon, <em>mirrored.</em>
        </h1>
        <p>
          Every kit part is authored with logical properties. Flip the toggle and the whole tree —
          including this page&apos;s chrome — mirrors: buttons and fields, Select and its inline
          popup, checkbox and switch, menus, dialog and both sheet sides, both tab systems (the
          TabStrip ink included), tooltips, pagers, tables with end-aligned numerics, badge tones,
          empty state, cards, and a pinned two-column layout.
        </p>
      </header>
      <RtlReference />
    </main>
  );
}
