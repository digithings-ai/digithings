import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Input,
} from "@digithings/web/ui";

/**
 * Wave 0 proof route — the stock shadcn set from @digithings/web/ui wearing the
 * Instrument-Panel skin. Deliberately no call-site classes on the components:
 * the classNames here are the reference scaffold on layout wrappers plus the
 * real .accent-digigraph livery scope (design/tokens.css), which exists to
 * prove the single `@theme inline` bridge re-resolves inside a scope.
 */
export default function UiProofPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// ui kit"}</p>
        <h1>
          Stock shadcn, <em>in the skin.</em>
        </h1>
        <p>
          Wave 0 proof of chain: <code>Button</code>, <code>Input</code>, <code>Card</code> and{" "}
          <code>Dialog</code> vendored from <code>@digithings/web/ui</code>, untouched at the call
          site and dressed only by the <code>web-theme.css</code> token bridge.
        </p>
      </header>

      <section className="section-block" id="proof-buttons">
        <p className="kicker">{"// button"}</p>
        <h2 className="title">Variants and sizes.</h2>
        <div className="btn-row">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
        </div>
        <div className="btn-row">
          <Button size="sm">Small</Button>
          <Button size="lg">Large</Button>
          <Button disabled>Disabled</Button>
        </div>
      </section>

      <section className="section-block" id="proof-input">
        <p className="kicker">{"// input"}</p>
        <h2 className="title">Search field.</h2>
        <div className="mt-[1.2rem] flex max-w-[26rem] flex-col gap-1.5">
          <label className="kicker" htmlFor="proof-search">
            Ticker
          </label>
          <Input id="proof-search" placeholder="Search tickers" />
        </div>
      </section>

      <section className="section-block" id="proof-card">
        <p className="kicker">{"// card"}</p>
        <h2 className="title">Container.</h2>
        <div className="mt-[1.2rem] max-w-[26rem]">
          <Card>
            <CardHeader>
              <CardTitle>Chain status</CardTitle>
              <CardDescription>Stock Card, flat and hairline-bordered.</CardDescription>
            </CardHeader>
            <CardContent>
              Depth comes from the hairline and the tonal step — no shadow on content.
            </CardContent>
            <CardFooter>Last checked 09:41 UTC</CardFooter>
          </Card>
        </div>
      </section>

      <section className="section-block" id="proof-dialog">
        <p className="kicker">{"// dialog"}</p>
        <h2 className="title">Floating overlay.</h2>
        <div className="btn-row">
          <Dialog>
            <DialogTrigger render={<Button variant="outline" />}>Open dialog</DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Overlay proof</DialogTitle>
                <DialogDescription>
                  The one surface allowed above the page — scrim behind, hairline ring, dismissed
                  by Escape or the scrim.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose render={<Button variant="ghost" />}>Close</DialogClose>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </section>

      <section className="section-block accent-digigraph" id="proof-livery">
        <p className="kicker">{"// livery scope — .accent-digigraph"}</p>
        <h2 className="title">Scoped livery re-resolves tokens.</h2>
        <p className="section-copy">
          Inside this section <code>--accent</code> is digigraph gold while{" "}
          <code>--color-primary</code> stays ink: the primary CTA never follows a livery, and the
          focus ring reads the scoped accent.
        </p>
        <div className="btn-row">
          <Button>Primary stays ink</Button>
          <Button variant="outline">Outline</Button>
        </div>
        <div className="mt-[1.2rem] flex max-w-[26rem] flex-col gap-1.5">
          <label className="kicker" htmlFor="proof-livery-search">
            Ticker
          </label>
          <Input id="proof-livery-search" placeholder="Search tickers" />
        </div>
      </section>
    </main>
  );
}
