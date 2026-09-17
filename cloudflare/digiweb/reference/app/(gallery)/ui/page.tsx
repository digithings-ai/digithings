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
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
  Label,
  Separator,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@digithings/web/ui";

/**
 * Wave 0 proof route and wave 1 extension — the stock shadcn set from
 * @digithings/web/ui wearing the Instrument-Panel skin. Deliberately no
 * call-site classes on the components: the classNames here are the reference
 * scaffold on layout wrappers plus the real .accent-digigraph livery scope
 * (design/tokens.css), which exists to prove the single `@theme inline` bridge
 * re-resolves inside a scope.
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
          Proof of chain: <code>Button</code>, <code>Input</code>, <code>Card</code>,{" "}
          <code>Dialog</code> and the wave-1 additions — <code>Textarea</code>, <code>Label</code>,{" "}
          <code>Separator</code>, <code>Badge</code>, <code>Alert</code>, <code>Tabs</code>,{" "}
          <code>Collapsible</code>, <code>Tooltip</code>, <code>DropdownMenu</code>,{" "}
          <code>Sheet</code> — vendored from <code>@digithings/web/ui</code>, untouched at the call
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
          <Label className="kicker" htmlFor="proof-search">
            Ticker
          </Label>
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

      <section className="section-block" id="proof-textarea">
        <p className="kicker">{"// textarea"}</p>
        <h2 className="title">Multi-line notes.</h2>
        <div className="mt-[1.2rem] max-w-[26rem]">
          <Textarea rows={3} placeholder="What is this run testing?" />
        </div>
      </section>

      <section className="section-block" id="proof-label">
        <p className="kicker">{"// label"}</p>
        <h2 className="title">Associated label.</h2>
        <div className="mt-[1.2rem] flex max-w-[26rem] flex-col gap-1.5">
          <Label htmlFor="proof-label-input">Strategy</Label>
          <Input id="proof-label-input" placeholder="trend_xsec" />
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

      <section className="section-block" id="proof-badge">
        <p className="kicker">{"// badge"}</p>
        <h2 className="title">Tones.</h2>
        <div className="mt-[1.2rem] flex flex-wrap gap-2">
          <Badge>Default</Badge>
          <Badge variant="secondary">Secondary</Badge>
          <Badge variant="destructive">Destructive</Badge>
          <Badge variant="outline">Outline</Badge>
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

      <section className="section-block" id="proof-collapsible">
        <p className="kicker">{"// collapsible"}</p>
        <h2 className="title">Disclosure.</h2>
        <div className="mt-[1.2rem] max-w-[26rem]">
          <Collapsible defaultOpen>
            <CollapsibleTrigger render={<Button variant="outline" />}>Details</CollapsibleTrigger>
            <CollapsibleContent>
              <div className="pt-2">The panel is mounted only while it is open.</div>
            </CollapsibleContent>
          </Collapsible>
        </div>
      </section>

      <section className="section-block" id="proof-tooltip">
        <p className="kicker">{"// tooltip"}</p>
        <h2 className="title">Hint on hover and focus.</h2>
        <TooltipProvider>
          <div className="mt-[1.2rem] flex flex-wrap gap-2">
            <Tooltip>
              <TooltipTrigger render={<Button variant="outline" />}>Top</TooltipTrigger>
              <TooltipContent side="top">Ships to paper first</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger render={<Button variant="outline" />}>Bottom</TooltipTrigger>
              <TooltipContent side="bottom">Gated behind a human</TooltipContent>
            </Tooltip>
          </div>
        </TooltipProvider>
      </section>

      <section className="section-block" id="proof-dropdown">
        <p className="kicker">{"// dropdown menu"}</p>
        <h2 className="title">Grouped items.</h2>
        <div className="mt-[1.2rem]">
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="outline" />}>
              Open menu
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuGroup>
                <DropdownMenuLabel>Strategy</DropdownMenuLabel>
                <DropdownMenuItem>trend_xsec</DropdownMenuItem>
                <DropdownMenuItem>breakout</DropdownMenuItem>
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuCheckboxItem defaultChecked>Audit logging</DropdownMenuCheckboxItem>
            </DropdownMenuContent>
          </DropdownMenu>
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
          <Label className="kicker" htmlFor="proof-livery-search">
            Ticker
          </Label>
          <Input id="proof-livery-search" placeholder="Search tickers" />
        </div>
      </section>
    </main>
  );
}
