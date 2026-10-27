import "./components.css";
import { Badge, Button, Input } from "@digithings/ui/ui";
import { kitIndex } from "@/lib/kit-index";

/**
 * Components — the kit, indexed from the package's own barrels.
 *
 * `kitIndex()` parses `packages/ui/src/ui/index.ts` and
 * `packages/ui/src/index.ts`, so the lists below are the exports that exist,
 * not a hand-maintained catalogue. `lib/kit-index.test.ts` guards the parser.
 */
export default function ComponentsPage() {
  const { primitives, composites } = kitIndex();

  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// components"}</p>
        <h1>
          The kit, <em>indexed.</em>
        </h1>
        <p>
          {primitives.length} primitives behind <code>@digithings/ui/ui</code> and{" "}
          {composites.length} modules behind <code>@digithings/ui</code>, read from the
          package&apos;s barrels at build time. A part that is not exported here is not part of the
          language yet.
        </p>
      </header>

      <section className="section-block">
        <h2 className="title">Proof</h2>
        <p className="section-copy">
          The primitives are kit parts, not app-local copies: same dress in every surface that
          imports them.
        </p>
        <div className="cp-proof">
          <div className="cp-row">
            <Button>Default</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="destructive">Destructive</Button>
            <Button variant="link">Link</Button>
          </div>
          <div className="cp-row">
            <Badge>default</Badge>
            <Badge variant="neutral">neutral</Badge>
            <Badge variant="accent">accent</Badge>
            <Badge variant="up">up</Badge>
            <Badge variant="down">down</Badge>
            <Badge variant="warn">warn</Badge>
          </div>
          <div className="cp-row">
            <Input placeholder="Input — one hairline, no shadow" className="cp-input" />
          </div>
        </div>
      </section>

      <section className="section-block">
        <h2 className="title">Primitives</h2>
        <p className="section-copy">
          Import from <code>@digithings/ui/ui</code>. Each row is one module in{" "}
          <code>packages/ui/src/ui/</code>.
        </p>
        <ul className="cp-list">
          {primitives.map((entry) => (
            <li key={entry.module}>
              <code className="cp-name">{entry.name}</code>
              <span className="cp-path">{entry.module}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="section-block">
        <h2 className="title">Modules</h2>
        <p className="section-copy">
          Import from <code>@digithings/ui</code>. Every module the main barrel re-exports —
          composites, motion, navigation and data helpers — relative to{" "}
          <code>packages/ui/src/</code>.
        </p>
        <ul className="cp-list cp-list--wide">
          {composites.map((entry) => (
            <li key={entry.module}>
              <span className="cp-path">{entry.module}</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
