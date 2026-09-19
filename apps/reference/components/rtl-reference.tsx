"use client";

/**
 * RtlReference — the canon RTL proof for the kit (phase 0.2, #4306).
 *
 * The kit is authored with logical properties, so this page is the standing
 * evidence: one toggle flips `<html dir>` (through the kit's `DirectionProvider
 * root`) and the whole canon below — plus the reference chrome around it —
 * mirrors. It exercises every family the preset asked `rtl=true` for: chrome,
 * buttons (all variants + sizes), form fields, Select + SelectPopup, checkbox
 * and switch, dropdown menu, dialog and both sheet sides, both tab systems
 * (including the TabStrip sliding ink), tooltip, pager/date-pager, a table with
 * end-aligned numerics and start-aligned row headers, badge tones, empty state,
 * cards/composites, and a two-column/pinned layout.
 *
 * The route does not import the kit's `DirectionProvider` as a wrapper — it
 * uses `root`, so the reference's own NavShell mirrors too.
 */
import { useState, type ReactNode } from "react";
import {
  Breadcrumbs,
  DatePager,
  DirectionProvider,
  EmptyState,
  Pagination,
  TabStrip,
  type TabItem,
} from "@digithings/ui";
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
  Checkbox,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
  Label,
  Select,
  SelectItem,
  SelectPopup,
  SelectTrigger,
  SelectValue,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableRowHeader,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@digithings/ui/ui";

const BUTTON_VARIANTS = ["default", "outline", "secondary", "ghost", "destructive", "link"] as const;
const BUTTON_SIZES = ["default", "xs", "sm", "lg", "icon", "icon-xs", "icon-sm", "icon-lg"] as const;
const BADGE_TONES = [
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

const TABS: TabItem[] = [
  { id: "overview", label: "Overview" },
  { id: "positions", label: "Positions" },
  { id: "fills", label: "Fills" },
  { id: "research", label: "Research" },
];

function Section({
  id,
  title,
  note,
  children,
}: {
  id: string;
  title: string;
  note?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24">
      <p className="kicker">{`// ${id}`}</p>
      <h2 className="title">{title}</h2>
      {note ? <p className="section-copy">{note}</p> : null}
      <div className="mt-[1.2rem]">{children}</div>
    </section>
  );
}

export function RtlReference() {
  const [dir, setDir] = useState<"ltr" | "rtl">("ltr");
  const [tab, setTab] = useState(0);
  const [date, setDate] = useState("2026-09-18");
  const [page, setPage] = useState(4);

  return (
    <DirectionProvider root dir={dir}>
      <div className="rtl-proof">
        <div className="rtl-row" role="group" aria-label="Direction">
          <Button
            size="sm"
            variant={dir === "ltr" ? "default" : "outline"}
            aria-pressed={dir === "ltr"}
            onClick={() => setDir("ltr")}
          >
            LTR
          </Button>
          <Button
            size="sm"
            variant={dir === "rtl" ? "default" : "outline"}
            aria-pressed={dir === "rtl"}
            onClick={() => setDir("rtl")}
          >
            RTL
          </Button>
          <span className="text-ink-mute text-[0.8rem]">
            direction: <code>dir=&quot;{dir}&quot;</code>
          </span>
        </div>

        <Section
          id="chrome"
          title="Chrome"
          note="Breadcrumb trail, pagination and a menu in the bar — all authored with logical insets."
        >
          <div className="rtl-grid">
            <div className="rtl-row">
              <Breadcrumbs
                items={[
                  { label: "Home", href: "#" },
                  { label: "Research", href: "#" },
                  { label: "Fills" },
                ]}
              />
            </div>
            <div className="rtl-row">
              <Pagination page={page} pageCount={9} onPageChange={setPage} />
            </div>
            <div className="rtl-row">
              <DropdownMenu>
                <DropdownMenuTrigger render={<Button variant="outline" size="sm" />}>
                  Actions
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  <DropdownMenuLabel>Run</DropdownMenuLabel>
                  <DropdownMenuItem>
                    Backtest
                    <span className="ml-auto text-ink-mute text-[0.7rem]">⌘B</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem>Optimize</DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem>Delete</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </Section>

        <Section
          id="buttons"
          title="Buttons — every variant and size"
          note="Variant and size axes are direction-agnostic; the icon paddings use inline-start/end so a leading or trailing glyph mirrors."
        >
          <div className="rtl-proof" style={{ gap: "0.75rem" }}>
            {BUTTON_VARIANTS.map((variant) => (
              <div key={variant} className="rtl-row">
                <span className="text-ink-mute w-[5.5rem] font-mono text-[0.7rem]">{variant}</span>
                {BUTTON_SIZES.map((size) => (
                  <Button key={size} variant={variant} size={size}>
                    {size.startsWith("icon") ? "→" : size}
                  </Button>
                ))}
              </div>
            ))}
          </div>
        </Section>

        <Section id="fields" title="Input, label, textarea" note="Label sits before the control; helper text hangs off the inline end.">
          <div className="rtl-two-col">
            <div className="flex flex-col gap-2">
              <Label htmlFor="rtl-ticker">Ticker</Label>
              <Input id="rtl-ticker" placeholder="BTC-PERP" />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="rtl-notes">Notes</Label>
              <Textarea id="rtl-notes" placeholder="Thesis, invalidation, size…" />
            </div>
          </div>
        </Section>

        <Section id="select" title="Select — incl. SelectPopup" note="The non-portal SelectPopup renders inline; the chevron and item check keep their inline-side slots.">
          <div className="rtl-row">
            <Select defaultValue="aapl" defaultOpen modal={false}>
              <SelectTrigger aria-label="Instrument">
                <SelectValue placeholder="Instrument" />
              </SelectTrigger>
              <SelectPopup>
                <SelectItem value="aapl">AAPL</SelectItem>
                <SelectItem value="btc">BTC-PERP</SelectItem>
                <SelectItem value="eth">ETH-PERP</SelectItem>
              </SelectPopup>
            </Select>
          </div>
        </Section>

        <Section id="toggles" title="Checkbox, switch" note="Controls with a start-side label; the switch thumb mirrors its checked travel.">
          <div className="rtl-row">
            <Label className="gap-2">
              <Checkbox defaultChecked aria-label="Include fees" /> Include fees
            </Label>
            <Label className="gap-2">
              <Checkbox aria-label="Include slippage" /> Include slippage
            </Label>
            <Label className="gap-2">
              <Switch defaultChecked aria-label="Live updates" /> Live updates
            </Label>
            <Label className="gap-2">
              <Switch size="sm" aria-label="Compact rows" /> Compact rows
            </Label>
          </div>
        </Section>

        <Section
          id="tabs"
          title="Tabs — stock list + sliding TabStrip"
          note="The stock Tabs underline is a pseudo-element; the TabStrip is the JS-measured sliding ink, made direction-aware."
        >
          <div className="rtl-proof" style={{ gap: "1.4rem" }}>
            <Tabs defaultValue="one">
              <TabsList>
                <TabsTrigger value="one">One</TabsTrigger>
                <TabsTrigger value="two">Two</TabsTrigger>
                <TabsTrigger value="three">Three</TabsTrigger>
              </TabsList>
              <TabsContent value="one">Panel one</TabsContent>
              <TabsContent value="two">Panel two</TabsContent>
              <TabsContent value="three">Panel three</TabsContent>
            </Tabs>

            <div>
              <TabStrip tabs={TABS} active={tab} onChange={setTab} label="RTL proof tabs" />
              <p className="mt-3 text-ink-mute text-[0.8rem]">
                active: <code>{TABS[tab].id}</code> — the ink should sit under this tab in both
                directions.
              </p>
            </div>

            <div>
              <TabStrip
                tabs={TABS}
                active={tab}
                onChange={setTab}
                label="RTL proof chips"
                variant="chip"
              />
            </div>

            <div>
              <TabStrip
                tabs={TABS}
                active={tab}
                onChange={setTab}
                label="RTL proof pill"
                variant="pill"
              />
            </div>
          </div>
        </Section>

        <Section id="overlays" title="Tooltip, dialog, sheet (both sides)" note="Tooltip arrow follows the placement; dialog is centered; sheet sides stay physical to the `side` prop.">
          <div className="rtl-row">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger render={<Button variant="outline" size="sm" />}>
                  Hover for tooltip
                </TooltipTrigger>
                <TooltipContent side="inline-end">Ships to paper first</TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <Dialog>
              <DialogTrigger render={<Button variant="destructive" size="sm" />}>
                Open dialog
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Delete this backtest?</DialogTitle>
                  <DialogDescription>
                    The run leaves the library index. Saved tearsheets are kept.
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <DialogClose render={<Button variant="ghost" />}>Cancel</DialogClose>
                  <DialogClose render={<Button variant="destructive" />}>Delete run</DialogClose>
                </DialogFooter>
              </DialogContent>
            </Dialog>

            <Sheet>
              <SheetTrigger render={<Button variant="outline" size="sm" />}>
                Open sheet · left
              </SheetTrigger>
              <SheetContent side="left">
                <SheetHeader>
                  <SheetTitle>Left sheet</SheetTitle>
                  <SheetDescription>Anchored to the physical left edge.</SheetDescription>
                </SheetHeader>
              </SheetContent>
            </Sheet>

            <Sheet>
              <SheetTrigger render={<Button variant="outline" size="sm" />}>
                Open sheet · right
              </SheetTrigger>
              <SheetContent side="right">
                <SheetHeader>
                  <SheetTitle>Right sheet</SheetTitle>
                  <SheetDescription>Anchored to the physical right edge.</SheetDescription>
                </SheetHeader>
              </SheetContent>
            </Sheet>
          </div>
        </Section>

        <Section id="pager" title="Pager / date-pager" note="Prev/next chevrons mirror; the calendar grid stays a grid.">
          <div className="rtl-row">
            <Pagination page={page} pageCount={12} onPageChange={setPage} />
            <DatePager value={date} onChange={setDate} />
          </div>
        </Section>

        <Section
          id="data"
          title="Table — numerics end-aligned, row headers start-aligned"
          note="`numeric` aligns to the inline end (right in LTR, left in RTL); TableRowHeader pins the start side."
        >
          <Table density="compact">
            <TableHeader>
              <TableRow>
                <TableHead>Instrument</TableHead>
                <TableHead numeric>Qty</TableHead>
                <TableHead numeric>Px</TableHead>
                <TableHead numeric>P&amp;L</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {[
                ["BTC-PERP", "1.20", "64,210.50", "+1.84%"],
                ["ETH-PERP", "18.00", "3,144.20", "−0.42%"],
                ["SOL-PERP", "240.0", "148.90", "+3.10%"],
              ].map(([sym, qty, px, pnl]) => (
                <TableRow key={sym}>
                  <TableRowHeader>{sym}</TableRowHeader>
                  <TableCell numeric>{qty}</TableCell>
                  <TableCell numeric>{px}</TableCell>
                  <TableCell numeric>{pnl}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>

        <Section id="badges" title="Badge tones" note="Every token-backed reference tone, including the money up/down pair.">
          <div className="rtl-row">
            {BADGE_TONES.map((tone) => (
              <Badge key={tone} variant={tone}>
                {tone}
              </Badge>
            ))}
          </div>
        </Section>

        <Section id="empty" title="Empty state" note="Centered hairline slab; text centered regardless of direction.">
          <EmptyState
            variant="no-results"
            title="No runs match"
            body="Loosen the filter or widen the date range."
            action={
              <Button variant="outline" size="sm">
                Clear filters
              </Button>
            }
          />
        </Section>

        <Section id="composites" title="Cards / composites" note="Card header, action slot and footer stack logically.">
          <div className="rtl-two-col">
            <Card>
              <CardHeader>
                <CardTitle>Paper account</CardTitle>
                <CardDescription>In-sample, illustrative only.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="rtl-row" style={{ justifyContent: "space-between" }}>
                  <span>Net liquidation</span>
                  <span className="tabular-nums">$104,210.55</span>
                </div>
              </CardContent>
              <CardFooter>
                <Button size="sm">Open account</Button>
              </CardFooter>
            </Card>
            <Alert>
              <AlertTitle>Read this first</AlertTitle>
              <AlertDescription>
                Figures are backtested and in-sample. Not investment advice.
              </AlertDescription>
            </Alert>
          </div>
        </Section>

        <Section
          id="pinned"
          title="Two-column / pinned layout"
          note="A sticky row-header column pins to the inline-start; numeric columns hang off the inline-end."
        >
          <div className="rtl-pinned">
            <table>
              <thead>
                <tr>
                  <th className="rtl-pin text-start">Strategy</th>
                  <th className="text-end">Sharpe</th>
                  <th className="text-end">Max DD</th>
                  <th className="text-end">CAGR</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["momentum-v3", "1.42", "−12.4%", "18.1%"],
                  ["carry-basis", "0.98", "−8.1%", "11.6%"],
                  ["mean-revert", "1.11", "−15.9%", "14.2%"],
                  ["vol-target", "1.63", "−6.7%", "21.4%"],
                ].map((row) => (
                  <tr key={row[0]}>
                    <th scope="row" className="rtl-pin text-start font-normal">
                      {row[0]}
                    </th>
                    <td className="text-end tabular-nums">{row[1]}</td>
                    <td className="text-end tabular-nums">{row[2]}</td>
                    <td className="text-end tabular-nums">{row[3]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      </div>
    </DirectionProvider>
  );
}
