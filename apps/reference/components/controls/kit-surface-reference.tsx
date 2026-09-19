import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Separator,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableRowHeader,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@digithings/ui/ui";

const BUTTON_VARIANTS = ["default", "secondary", "outline", "ghost", "destructive", "link"] as const;
const BADGE_VARIANTS = [
  "default",
  "secondary",
  "destructive",
  "outline",
  "ghost",
  "link",
  "neutral",
  "accent",
  "warn",
  "up",
  "down",
] as const;

const LEDGER = [
  { symbol: "BTC-PERP", side: "long", qty: "0.84", pf: "2.31", pnl: "+18.4%" },
  { symbol: "ETH-PERP", side: "long", qty: "12.0", pf: "1.74", pnl: "+6.2%" },
  { symbol: "SOL-PERP", side: "short", qty: "220", pf: "0.91", pnl: "−4.8%" },
];

/**
 * The kit's current surface, in one canonical specimen. This is the former
 * `/ui` proof route folded into `/controls` (workstream A, #4306): rather than
 * two competing "kit proof" pages, every `@digithings/ui/ui` part is shown
 * exactly once across the controls route, and this specimen covers the parts
 * added after the original `/ui` page was written — the `Table` grammar
 * (`density`, `numeric`, `TableRowHeader`, `interactive`), every `Badge`
 * variant and tone, and the `Sheet` overlay.
 *
 * Parts with a dedicated sibling specimen are deliberately absent here:
 * Input/Label/Textarea/Checkbox/Switch (`form-fields-reference`), Select
 * (`select-reference`), DropdownMenu (`dropdown-reference`), Dialog
 * (`dialog-reference`), Tooltip (`tooltip-reference`), Collapsible
 * (`accordion-reference`). See `lib/specimen-inventory.ts` for the mapping.
 */
export function KitSurfaceReference() {
  return (
    <>
      <section className="section-block" id="proof-button">
        <p className="kicker">{"// button"}</p>
        <h2 className="title">Variants, tones and sizes.</h2>
        <p className="section-copy">
          <code>Button</code> from <code>@digithings/ui/ui</code> — stock variants, stock sizes,
          untouched at the call site.
        </p>
        <div className="btn-row mt-[1.2rem]">
          {BUTTON_VARIANTS.map((variant) => (
            <Button key={variant} variant={variant}>
              {variant}
            </Button>
          ))}
        </div>
        <div className="btn-row mt-[0.6rem]">
          <Button size="xs">xs</Button>
          <Button size="sm">sm</Button>
          <Button size="default">default</Button>
          <Button size="lg">lg</Button>
          <Button disabled>Disabled</Button>
        </div>
      </section>

      <section className="section-block" id="proof-badge">
        <p className="kicker">{"// badge"}</p>
        <h2 className="title">Every variant and tone.</h2>
        <p className="section-copy">
          <code>Badge</code> carries the shadcn variants plus the reference-dress tones added in
          wave 4 — <code>neutral</code>, <code>accent</code>, <code>warn</code>, <code>up</code>,{" "}
          <code>down</code> — all token-backed.
        </p>
        <div className="mt-[1.2rem] flex flex-wrap gap-2">
          {BADGE_VARIANTS.map((variant) => (
            <Badge key={variant} variant={variant}>
              {variant}
            </Badge>
          ))}
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
            <CardFooter>
              <Badge variant="accent">core</Badge>
            </CardFooter>
          </Card>
        </div>
      </section>

      <section className="section-block" id="proof-separator">
        <p className="kicker">{"// separator"}</p>
        <h2 className="title">Hairline rule.</h2>
        <div className="mt-[1.2rem] flex max-w-[26rem] flex-col gap-2">
          <p>Above the rule.</p>
          <Separator />
          <p>Below the rule.</p>
        </div>
      </section>

      <section className="section-block" id="proof-alert">
        <p className="kicker">{"// alert"}</p>
        <h2 className="title">Inline notice.</h2>
        <div className="mt-[1.2rem] flex max-w-[26rem] flex-col gap-2">
          <Alert>
            <AlertTitle>Paper route confirmed</AlertTitle>
            <AlertDescription>
              The run ships to paper before anything touches a broker.
            </AlertDescription>
          </Alert>
          <Alert variant="destructive">
            <AlertTitle>Key revoked</AlertTitle>
            <AlertDescription>Issue a new key before the next backtest.</AlertDescription>
          </Alert>
        </div>
      </section>

      <section className="section-block" id="proof-tabs">
        <p className="kicker">{"// tabs"}</p>
        <h2 className="title">One panel at a time.</h2>
        <p className="section-copy">
          The in-page <code>Tabs</code> primitive. Chrome navigation uses{" "}
          <code>TabStrip</code> instead — a different part for a different surface.
        </p>
        <div className="mt-[1.2rem] max-w-[26rem]">
          <Tabs defaultValue="backtest">
            <TabsList>
              <TabsTrigger value="backtest">Backtest</TabsTrigger>
              <TabsTrigger value="paper">Paper</TabsTrigger>
              <TabsTrigger value="live">Live</TabsTrigger>
            </TabsList>
            <TabsContent value="backtest">
              Deterministic tearsheets on a NautilusTrader core.
            </TabsContent>
            <TabsContent value="paper">Ships to paper first; the ledger replays exactly.</TabsContent>
            <TabsContent value="live">Every live rung is a human gate.</TabsContent>
          </Tabs>
        </div>
      </section>

      <section className="section-block" id="proof-sheet">
        <p className="kicker">{"// sheet"}</p>
        <h2 className="title">Edge panel.</h2>
        <div className="mt-[1.2rem]">
          <Sheet>
            <SheetTrigger render={<Button variant="outline" />}>Open sheet</SheetTrigger>
            <SheetContent side="right">
              <SheetHeader>
                <SheetTitle>Edge panel</SheetTitle>
                <SheetDescription>
                  Slides in from the right on the kit&apos;s own transition.
                </SheetDescription>
              </SheetHeader>
            </SheetContent>
          </Sheet>
        </div>
      </section>

      <section className="section-block" id="proof-table">
        <p className="kicker">{"// table"}</p>
        <h2 className="title">The ledger grammar.</h2>
        <p className="section-copy">
          The stock <code>Table</code>: <code>density=&quot;compact&quot;</code> halves the row
          padding, <code>numeric</code> right-aligns and turns on tabular figures,{" "}
          <code>TableRowHeader</code> names the row, and <code>interactive</code> opts a row into
          the pointer cursor. Composite tables (sortable, precision, pricing) live on the{" "}
          <a href="/data">data page</a>.
        </p>
        <div className="mt-[1.2rem] max-w-[34rem]">
          <Table>
            <TableCaption>Default density — hover the third row.</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>Side</TableHead>
                <TableHead numeric>Qty</TableHead>
                <TableHead numeric>PF</TableHead>
                <TableHead numeric>P&amp;L</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {LEDGER.map((row, i) => (
                <TableRow key={row.symbol} interactive={i === 2}>
                  <TableRowHeader>{row.symbol}</TableRowHeader>
                  <TableCell>{row.side}</TableCell>
                  <TableCell numeric>{row.qty}</TableCell>
                  <TableCell numeric>{row.pf}</TableCell>
                  <TableCell numeric>{row.pnl}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <div className="mt-[1.4rem] max-w-[34rem]">
          <Table density="compact">
            <TableCaption>Compact density — the same parts, half the padding.</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Metric</TableHead>
                <TableHead numeric>Value</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableRowHeader>CAGR</TableRowHeader>
                <TableCell numeric>+44.9%</TableCell>
              </TableRow>
              <TableRow>
                <TableRowHeader>Sharpe</TableRowHeader>
                <TableCell numeric>2.31</TableCell>
              </TableRow>
              <TableRow>
                <TableRowHeader>Max drawdown</TableRowHeader>
                <TableCell numeric>−18.4%</TableCell>
              </TableRow>
            </TableBody>
          </Table>
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
        <div className="mt-[1.2rem] flex flex-wrap gap-2">
          <Badge variant="accent">scoped accent</Badge>
          <Badge variant="neutral">neutral</Badge>
        </div>
      </section>
    </>
  );
}
