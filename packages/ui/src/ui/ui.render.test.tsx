import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardContent,
  Checkbox,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  EmptyState,
  Field,
  IconButton,
  Input,
  Label,
  Radio,
  RadioGroup,
  SegmentedControl,
  Select,
  SelectContent,
  SelectItem,
  SelectPopup,
  SelectTrigger,
  SelectValue,
  Separator,
  Sheet,
  SheetContent,
  SheetTrigger,
  Skeleton,
  SkeletonGroup,
  Slider,
  Switch,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableRowHeader,
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./index";
import {
  Avatar,
  AvatarBadge,
  AvatarFallback,
  AvatarGroup,
  AvatarGroupCount,
  AvatarImage,
  Breadcrumbs,
  DatePager,
  Form,
  FormActions,
  FormField,
  Pagination,
  Pager,
  PagerPage,
  SearchBar,
  TagsInput,
  formatDatePagerLabel,
  paginationWindow,
} from "./index";

describe("vendored ui kit renders server-side", () => {
  it("Button keeps the shadcn data-slot contract", () => {
    const html = renderToStaticMarkup(<Button>Run</Button>);
    expect(html).toContain('data-slot="button"');
    expect(html).toContain("Run");
  });

  it("Card composes parts", () => {
    const html = renderToStaticMarkup(
      <Card>
        <CardContent>body</CardContent>
      </Card>,
    );
    expect(html).toContain('data-slot="card"');
    expect(html).toContain("body");
  });

  it("Input renders with the input slot", () => {
    const html = renderToStaticMarkup(<Input placeholder="ticker" />);
    expect(html).toContain('data-slot="input"');
  });

  it("Textarea renders with the textarea slot", () => {
    const html = renderToStaticMarkup(<Textarea placeholder="notes" />);
    expect(html).toContain('data-slot="textarea"');
  });

  it("Label renders with the label slot", () => {
    const html = renderToStaticMarkup(<Label htmlFor="ticker">Ticker</Label>);
    expect(html).toContain('data-slot="label"');
    expect(html).toContain('for="ticker"');
  });

  it("Separator renders with the separator slot", () => {
    const html = renderToStaticMarkup(<Separator />);
    expect(html).toContain('data-slot="separator"');
  });

  it("Badge renders with the badge slot", () => {
    const html = renderToStaticMarkup(<Badge>live</Badge>);
    expect(html).toContain('data-slot="badge"');
    expect(html).toContain("live");
  });

  it("Badge tone variants render the token-backed reference tones", () => {
    expect(renderToStaticMarkup(<Badge variant="neutral">flat</Badge>)).toContain(
      "text-ink-mute",
    );
    expect(renderToStaticMarkup(<Badge variant="accent">core</Badge>)).toContain(
      "border-accent-weak text-accent",
    );
    expect(renderToStaticMarkup(<Badge variant="warn">roadmap</Badge>)).toContain(
      "text-warn",
    );
    expect(renderToStaticMarkup(<Badge variant="up">+2.4%</Badge>)).toContain(
      "border-up/40 text-up",
    );
    expect(renderToStaticMarkup(<Badge variant="down">−1.1%</Badge>)).toContain(
      "border-down/40 text-down",
    );
  });

  it("Checkbox renders its root and (when checked) the indicator", () => {
    const checked = renderToStaticMarkup(<Checkbox defaultChecked aria-label="Enable" />);
    expect(checked).toContain('data-slot="checkbox"');
    expect(checked).toContain('data-slot="checkbox-indicator"');
    const unchecked = renderToStaticMarkup(<Checkbox aria-label="Enable" />);
    expect(unchecked).toContain('data-slot="checkbox"');
  });

  it("Switch renders its root, size hook and thumb", () => {
    const html = renderToStaticMarkup(<Switch size="sm" aria-label="Toggle" />);
    expect(html).toContain('data-slot="switch"');
    expect(html).toContain('data-slot="switch-thumb"');
    expect(html).toContain('data-size="sm"');
  });

  it("dress=\"chat\" emits the digichat ctl-*-chat dress classes", () => {
    expect(
      renderToStaticMarkup(
        <Button dress="chat" variant="outline" size="sm">
          Go
        </Button>,
      ),
    ).toContain("ctl-btn-chat--outline ctl-btn-chat--size-sm");
    expect(renderToStaticMarkup(<Badge dress="chat" variant="secondary">x</Badge>)).toContain(
      "ctl-badge-chat--secondary",
    );
    expect(renderToStaticMarkup(<Input dress="chat" />)).toContain("ctl-input-chat");
    expect(renderToStaticMarkup(<Label dress="chat">L</Label>)).toContain("ctl-label-chat");
    const card = renderToStaticMarkup(
      <Card dress="chat">
        <CardContent>body</CardContent>
      </Card>,
    );
    expect(card).toContain("ctl-card-chat");
    expect(card).toContain("ctl-card-content");
  });

  it("Table composes header, body, row and cells", () => {
    const html = renderToStaticMarkup(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Ticker</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>AAPL</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    expect(html).toContain('data-slot="table"');
    expect(html).toContain('data-slot="table-container"');
    expect(html).toContain('data-slot="table-header"');
    expect(html).toContain('data-slot="table-body"');
    expect(html).toContain('data-slot="table-row"');
    expect(html).toContain('data-slot="table-head"');
    expect(html).toContain('data-slot="table-cell"');
    expect(html).toContain("AAPL");
  });

  it("Table numeric cells end-align with tabular figures", () => {
    const html = renderToStaticMarkup(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead numeric>size</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell numeric>1.20</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    expect(html).toContain("text-end tabular-nums");
  });

  it("Table head and cells carry logical start alignment, never physical text-left", () => {
    const html = renderToStaticMarkup(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>ticker</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableRowHeader>BTC-PERP</TableRowHeader>
            <TableCell>1.20</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    expect(html).toContain("text-start");
    expect(html).not.toContain("text-left");
  });

  it("Button size paddings use logical inline padding (ps/pe)", () => {
    const html = renderToStaticMarkup(<Button size="sm">Go</Button>);
    expect(html).toContain("ps-1.5");
    expect(html).not.toContain("pl-1.5");
  });

  it("Switch thumb mirrors its checked travel under dir=rtl", () => {
    const html = renderToStaticMarkup(<Switch aria-label="toggle" />);
    expect(html).toContain(
      "rtl:group-data-[size=default]/switch:data-checked:-translate-x-[calc(100%-2px)]",
    );
    expect(html).toContain(
      "rtl:group-data-[size=sm]/switch:data-checked:-translate-x-[calc(100%-2px)]",
    );
  });

  // Pointer cursors are a kit-level convention (#4306, phase 0.3): every
  // interactive part sets `cursor-pointer`, and disabled parts name the
  // `not-allowed` affordance rather than leaving the base cursor on.
  it("Button carries the kit pointer cursor and the disabled not-allowed contract", () => {
    const enabled = renderToStaticMarkup(<Button>Run</Button>);
    expect(enabled).toContain("cursor-pointer");
    const disabled = renderToStaticMarkup(<Button disabled>Run</Button>);
    expect(disabled).toContain("disabled:cursor-not-allowed");
  });

  it("TabsTrigger carries the pointer cursor and disabled/aria-disabled contract", () => {
    const html = renderToStaticMarkup(
      <Tabs defaultValue="one">
        <TabsList>
          <TabsTrigger value="one">One</TabsTrigger>
        </TabsList>
      </Tabs>,
    );
    expect(html).toContain("cursor-pointer");
    expect(html).toContain("disabled:cursor-not-allowed");
    expect(html).toContain("aria-disabled:cursor-not-allowed");
  });

  it("Switch and Checkbox carry the pointer cursor and disabled contract", () => {
    const sw = renderToStaticMarkup(<Switch aria-label="toggle" />);
    expect(sw).toContain("cursor-pointer");
    expect(sw).toContain("data-disabled:cursor-not-allowed");
    const cb = renderToStaticMarkup(<Checkbox aria-label="check" />);
    expect(cb).toContain("cursor-pointer");
    expect(cb).toContain("disabled:cursor-not-allowed");
  });

  it("CollapsibleTrigger renders the kit pointer cursor by default", () => {
    const html = renderToStaticMarkup(
      <Collapsible>
        <CollapsibleTrigger>More</CollapsibleTrigger>
      </Collapsible>,
    );
    expect(html).toContain("cursor-pointer");
    expect(html).toContain("disabled:cursor-not-allowed");
  });

  it("SelectTrigger and SelectItem carry the pointer cursor", () => {
    const html = renderToStaticMarkup(
      <Select defaultValue="aapl" defaultOpen>
        <SelectTrigger>
          <SelectValue placeholder="Ticker" />
        </SelectTrigger>
        <SelectPopup>
          <SelectItem value="aapl">AAPL</SelectItem>
        </SelectPopup>
      </Select>,
    );
    expect(html.match(/cursor-pointer/g)?.length ?? 0).toBeGreaterThanOrEqual(2);
  });

  it("TableRow is interactive only when asked; the pointer cursor is opt-in", () => {
    const plain = renderToStaticMarkup(
      <Table>
        <TableBody>
          <TableRow>
            <TableCell>1.20</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    expect(plain).not.toContain("cursor-pointer");

    const clickable = renderToStaticMarkup(
      <Table>
        <TableBody>
          <TableRow interactive>
            <TableCell>1.20</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    expect(clickable).toContain("cursor-pointer");
    expect(clickable).toContain('data-interactive="true"');
  });

  it("Table density=compact emits the density hook and compact padding", () => {
    const html = renderToStaticMarkup(
      <Table density="compact">
        <TableBody>
          <TableRow>
            <TableCell>1.20</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    expect(html).toContain('data-density="compact"');
    expect(html).toContain("[data-slot=table-cell]]:py-1");
  });

  it("TableRowHeader renders a scoped row header inside a body row", () => {
    const html = renderToStaticMarkup(
      <Table>
        <TableBody>
          <TableRow>
            <TableRowHeader>BTC-PERP</TableRowHeader>
            <TableCell>1.20</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    expect(html).toContain('data-slot="table-row-header"');
    expect(html).toMatch(/<th[^>]*scope="row"/);
    expect(html).toContain("BTC-PERP");
  });

  it("Alert composes parts", () => {
    const html = renderToStaticMarkup(
      <Alert>
        <AlertTitle>Heads up</AlertTitle>
        <AlertDescription>body</AlertDescription>
      </Alert>,
    );
    expect(html).toContain('data-slot="alert"');
    expect(html).toContain('data-slot="alert-title"');
    expect(html).toContain('data-slot="alert-description"');
  });

  it("Tabs renders list, triggers and the active panel", () => {
    const html = renderToStaticMarkup(
      <Tabs defaultValue="one">
        <TabsList>
          <TabsTrigger value="one">One</TabsTrigger>
          <TabsTrigger value="two">Two</TabsTrigger>
        </TabsList>
        <TabsContent value="one">Panel one</TabsContent>
        <TabsContent value="two">Panel two</TabsContent>
      </Tabs>,
    );
    expect(html).toContain('data-slot="tabs"');
    expect(html).toContain('data-slot="tabs-list"');
    expect(html).toContain('data-slot="tabs-trigger"');
    expect(html).toContain("Panel one");
    expect(html).not.toContain("Panel two");
  });

  it("TabsList contains its own overflow so a long list cannot widen the page", () => {
    // The reference audit's /account @390 critical: a 6-tab list was 459px with
    // overflow-x:visible, so the whole page scrolled (scrollWidth 494 > 390).
    // The list must scroll within itself (`max-w-full` caps it to its track,
    // `overflow-x-auto` makes the excess internal); it still shrink-wraps
    // (`w-fit`) when there is room, so desktop is untouched.
    const html = renderToStaticMarkup(
      <Tabs defaultValue="one">
        <TabsList>
          <TabsTrigger value="one">One</TabsTrigger>
        </TabsList>
      </Tabs>,
    );
    expect(html).toContain("max-w-full");
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain("w-fit");
  });

  it("Collapsible renders its panel only while open", () => {
    const open = renderToStaticMarkup(
      <Collapsible defaultOpen>
        <CollapsibleTrigger>More</CollapsibleTrigger>
        <CollapsibleContent>Body</CollapsibleContent>
      </Collapsible>,
    );
    expect(open).toContain('data-slot="collapsible"');
    expect(open).toContain('data-slot="collapsible-trigger"');
    expect(open).toContain('data-slot="collapsible-content"');

    const closed = renderToStaticMarkup(
      <Collapsible>
        <CollapsibleTrigger>More</CollapsibleTrigger>
        <CollapsibleContent>Body</CollapsibleContent>
      </Collapsible>,
    );
    expect(closed).toContain('data-slot="collapsible-trigger"');
    expect(closed).not.toContain('data-slot="collapsible-content"');
  });

  it("Select composes its trigger, selected value and icon; content is portal-only", () => {
    const html = renderToStaticMarkup(
      <Select defaultValue="aapl">
        <SelectTrigger>
          <SelectValue placeholder="Ticker" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="aapl">AAPL</SelectItem>
          <SelectItem value="msft">MSFT</SelectItem>
        </SelectContent>
      </Select>,
    );
    // The trigger composes in SSR: the value slot renders the selected value,
    // and the chevron icon is mounted. The item list lives in the portal, which
    // react-dom/server omits — so the unselected item's label must be absent.
    expect(html).toContain('data-slot="select-trigger"');
    expect(html).toContain('data-slot="select-value"');
    expect(html).toContain("aapl");
    expect(html).toMatch(/<svg/);
    expect(html).not.toContain("MSFT");
    expect(html).not.toContain('data-slot="select-content"');
  });

  it("SelectPopup composes items inline and SelectItem renders exactly one indicator", () => {
    const html = renderToStaticMarkup(
      <Select defaultValue="aapl" defaultOpen>
        <SelectTrigger>
          <SelectValue placeholder="Ticker" />
        </SelectTrigger>
        <SelectPopup>
          <SelectItem value="aapl">AAPL</SelectItem>
          <SelectItem value="msft">MSFT</SelectItem>
        </SelectPopup>
      </Select>,
    );
    // Unlike the stock portal-only SelectContent, the controls-parity
    // SelectPopup renders its positioner/popup inline, so the open list is
    // visible to react-dom/server.
    expect(html).toContain('data-slot="select-trigger"');
    expect(html).toContain('data-slot="select-popup"');
    expect(html).toContain('data-slot="select-item"');
    // SelectItem renders its own SelectItemIndicator; call sites must NOT pass
    // a second <SelectItemIndicator/> child (the P1 report's double-render
    // warning). SSR mounts only the selected item's indicator — assert the
    // exact count, not mere presence.
    expect(html.match(/data-slot="select-item-indicator"/g) ?? []).toHaveLength(1);
    expect(html).toContain("AAPL");
    expect(html).toContain("MSFT");
  });

  // Sheet, DropdownMenu and Tooltip content render through Base UI portals,
  // which react-dom/server omits; only their triggers can be asserted as
  // markup, and the content parts are asserted as exported symbols instead.
  it("Tooltip renders its trigger; content is portal-only", () => {
    const html = renderToStaticMarkup(
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>Hover</TooltipTrigger>
          <TooltipContent>Tip body</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    );
    expect(html).toContain('data-slot="tooltip-trigger"');
    expect(html).not.toContain('data-slot="tooltip-content"');
    expect(typeof TooltipContent).toBe("function");
  });

  it("Sheet renders its trigger; content is portal-only", () => {
    const html = renderToStaticMarkup(
      <Sheet>
        <SheetTrigger>Open</SheetTrigger>
        <SheetContent>Panel body</SheetContent>
      </Sheet>,
    );
    expect(html).toContain('data-slot="sheet-trigger"');
    expect(html).not.toContain('data-slot="sheet-content"');
    expect(typeof SheetContent).toBe("function");
  });

  it("DropdownMenu renders its trigger; content is portal-only", () => {
    const html = renderToStaticMarkup(
      <DropdownMenu>
        <DropdownMenuTrigger>Menu</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem>Item</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    expect(html).toContain('data-slot="dropdown-menu-trigger"');
    expect(html).not.toContain('data-slot="dropdown-menu-content"');
    expect(typeof DropdownMenuContent).toBe("function");
  });
});

describe("kit parts promoted from the controls layer (#4306, batch K1)", () => {
  it("Slider composes the Base UI track/range/thumb with the accent mechanism", () => {
    const html = renderToStaticMarkup(<Slider value={40} min={0} max={100} aria-label="cap" />);
    expect(html).toContain('data-slot="slider"');
    expect(html).toContain('data-slot="slider-track"');
    expect(html).toContain('data-slot="slider-range"');
    expect(html).toContain('data-slot="slider-thumb"');
    // the whole slider is the interactive affordance: pointer cursor on track
    // and thumb, not-allowed when disabled (kit cursor contract, 0.3).
    expect(html).toContain("cursor-pointer");
    expect(html).toContain("data-disabled:cursor-not-allowed");
  });

  it("Slider renders one thumb for a scalar value and one per range entry", () => {
    const single = renderToStaticMarkup(<Slider value={40} aria-label="single" />);
    expect(single.match(/data-slot="slider-thumb"/g) ?? []).toHaveLength(1);
    const range = renderToStaticMarkup(<Slider defaultValue={[25, 50]} aria-label="range" />);
    expect(range.match(/data-slot="slider-thumb"/g) ?? []).toHaveLength(2);
  });

  it("Slider positions thumbs with logical inline coordinates (RTL-safe)", () => {
    const html = renderToStaticMarkup(<Slider value={40} aria-label="cap" />);
    expect(html).toContain("inset-inline-start");
    expect(html).not.toContain("inset-left");
  });

  it("EmptyState renders the variant glyph, title, body, note and action", () => {
    const html = renderToStaticMarkup(
      <EmptyState
        variant="first-run"
        title="Nothing here yet"
        body="Run your first backtest."
        note="Results appear in the vault."
        action={<button type="button">New backtest</button>}
      />,
    );
    expect(html).toContain('data-slot="empty-state"');
    expect(html).toContain("Nothing here yet");
    expect(html).toContain("Run your first backtest.");
    expect(html).toContain("Results appear in the vault.");
    expect(html).toContain("New backtest");
    expect(html).toMatch(/<svg/);
  });

  it("EmptyState spends the danger tone only on the error variant and announces it", () => {
    const error = renderToStaticMarkup(<EmptyState variant="error" title="Boom" />);
    expect(error).toContain('role="alert"');
    expect(error).toContain("bg-danger/12");
    const calm = renderToStaticMarkup(<EmptyState variant="no-results" title="None" />);
    expect(calm).not.toContain("bg-danger/12");
    expect(calm).not.toContain('role="alert"');
  });

  it("EmptyState glass dresses drop the glyph disc unless an icon is passed", () => {
    const glass = renderToStaticMarkup(<EmptyState variant="error" dress="glass" title="Quiet" />);
    expect(glass).toContain("justify-center");
    expect(glass).not.toMatch(/<svg/);
    const withIcon = renderToStaticMarkup(
      <EmptyState variant="error" dress="glass" icon={<span>!</span>} title="Quiet" />,
    );
    expect(withIcon).toContain("!");
  });

  it("EmptyState glass-display is fluid and wrap-safe so the gate card cannot clip its title (#4452)", () => {
    const html = renderToStaticMarkup(
      <EmptyState
        variant="error"
        dress="glass-display"
        className="mx-auto max-w-md"
        title="Live data is not connected in this build"
        body="This deployment has no live data backend configured."
      />,
    );
    // Fluid: the card fills its container up to the consumer's cap. Without
    // this it can size to content and push past a phone-width viewport.
    expect(html).toContain("w-full");
    // Wrap-safe: a long unbreakable token must break, not overflow the box.
    expect(html).toContain("break-words");
    // A text-first gate card may never ellipsise the message it exists to state.
    // Scope to the message elements — an action Button may carry its own
    // `whitespace-nowrap` for its label without truncating the gate's copy.
    const title = html.match(/<h3[^>]*class="([^"]*)"/)?.[1] ?? "";
    const body = html.match(/<p[^>]*class="([^"]*)"/)?.[1] ?? "";
    for (const cls of [title, body]) {
      expect(cls).not.toContain("truncate");
      expect(cls).not.toMatch(/whitespace-nowrap|text-ellipsis|line-clamp/);
    }
  });

  it("Skeleton renders the shimmer shape with aria-hidden and no loading semantics", () => {
    const line = renderToStaticMarkup(<Skeleton className="h-3 w-40" />);
    expect(line).toContain('data-slot="skeleton"');
    expect(line).toContain('aria-hidden="true"');
    expect(line).toContain("motion-reduce:animate-none");
    const circle = renderToStaticMarkup(<Skeleton variant="circle" />);
    expect(circle).toContain("rounded-full");
    expect(renderToStaticMarkup(<Skeleton variant="block" />)).toContain("h-6");
    expect(renderToStaticMarkup(<Skeleton size="sm" />)).toContain("h-[0.5rem]");
  });

  it("SkeletonGroup carries the aria-busy loading contract", () => {
    const busy = renderToStaticMarkup(
      <SkeletonGroup className="flex flex-col">
        <Skeleton />
      </SkeletonGroup>,
    );
    expect(busy).toContain('data-slot="skeleton-group"');
    expect(busy).toContain('aria-busy="true"');
    expect(renderToStaticMarkup(<SkeletonGroup busy={false} />)).toContain('aria-busy="false"');
  });

  it("RadioGroup and Radio carry the pointer cursor and disabled contract", () => {
    const html = renderToStaticMarkup(
      <RadioGroup defaultValue="paper" aria-label="mode">
        <Radio value="paper" aria-label="paper" />
      </RadioGroup>,
    );
    expect(html).toContain('data-slot="radio-group"');
    expect(html).toContain('data-slot="radio"');
    expect(html).toContain("cursor-pointer");
    expect(html).toContain("data-disabled:cursor-not-allowed");
  });

  it("Field wires label, hint and error into the child control", () => {
    const html = renderToStaticMarkup(
      <Field label="Ticker" hint="Lowercase.">
        <input name="ticker" />
      </Field>,
    );
    expect(html).toContain('data-slot="field"');
    expect(html).toMatch(/<label[^>]*for="/);
    expect(html).toContain("Lowercase.");
    expect(html).toMatch(/aria-describedby="/);
  });

  it("Field swaps the hint for the error and marks the control invalid", () => {
    const html = renderToStaticMarkup(
      <Field label="Ticker" hint="Lowercase." error="Required.">
        <input name="ticker" />
      </Field>,
    );
    expect(html).toContain("Required.");
    expect(html).not.toContain("Lowercase.");
    expect(html).toContain('aria-invalid="true"');
    expect(html).toContain('data-invalid="true"');
  });

  it("Field marks required with a visible star and a screen-reader line", () => {
    const html = renderToStaticMarkup(
      <Field label="Ticker" required>
        <input name="ticker" />
      </Field>,
    );
    expect(html).toContain("*");
    expect(html).toContain("(required)");
    expect(html).toContain("sr-only");
  });

  it("IconButton is a borderless pointer glyph button with the disabled contract", () => {
    const html = renderToStaticMarkup(
      <IconButton aria-label="refresh">
        <svg />
      </IconButton>,
    );
    expect(html).toContain('data-slot="icon-button"');
    expect(html).toContain('aria-label="refresh"');
    expect(html).toContain("cursor-pointer");
    expect(html).toContain("disabled:cursor-not-allowed");
  });

  it("SegmentedControl is a pressed-button group (not a tablist) with pointer cells", () => {
    const html = renderToStaticMarkup(
      <SegmentedControl options={["1D", "1M", "All"]} value="1M" aria-label="Range" />,
    );
    expect(html).toContain('role="group"');
    expect(html).toContain('data-slot="segmented"');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('aria-pressed="false"');
    expect(html).not.toContain('role="tablist"');
    expect(html).toContain("cursor-pointer");
  });

  it("SegmentedControl accent dress reproduces the dashboard wash and type", () => {
    const html = renderToStaticMarkup(
      <SegmentedControl dress="accent" options={["a", "b"]} value="a" />,
    );
    expect(html).toContain("aria-pressed:bg-accent/20");
    expect(html).toContain("font-sans");
  });
});

describe("kit parts promoted from the controls layer (#4306, batch K2)", () => {
  it("Breadcrumbs renders the trail with a current page and slash separators", () => {
    const html = renderToStaticMarkup(
      <Breadcrumbs
        items={[{ label: "Pipeline", href: "/#pipeline" }, { label: "Research" }]}
      />,
    );
    expect(html).toContain('data-slot="breadcrumbs"');
    expect(html).toContain('aria-label="Breadcrumb"');
    expect(html).toContain('aria-current="page"');
    expect(html).toContain("<nav");
    expect(html).toContain("<ol");
    // the trail link is a pointer affordance with the canon focus ring
    expect(html).toContain("cursor-pointer");
    expect(html).toContain("focus-visible:ring-accent/30");
  });

  it("Pagination renders the window with the loud current page and edge steps", () => {
    const html = renderToStaticMarkup(
      <Pagination page={5} pageCount={12} onPageChange={() => {}} />,
    );
    expect(html).toContain('data-slot="pagination"');
    expect(html).toContain('aria-label="Pagination"');
    expect(html).toContain('aria-current="page"');
    expect(html).toContain('aria-label="Previous page"');
    expect(html).toContain('aria-label="Next page"');
    expect(html).toContain("bg-ink");
    expect(html).toContain("cursor-pointer");
  });

  it("Pagination disables prev on the first page and renders links with hrefForPage", () => {
    const html = renderToStaticMarkup(
      <Pagination page={1} pageCount={4} hrefForPage={(p) => `/log?p=${p}`} />,
    );
    expect(html).toContain("disabled");
    expect(html).toContain('href="/log?p=2"');
  });

  it("paginationWindow computes the ellipsis window", () => {
    expect(paginationWindow(5, 12)).toEqual([1, "…", 4, 5, 6, "…", 12]);
    expect(paginationWindow(1, 3)).toEqual([1, 2, 3]);
    expect(paginationWindow(2, 2)).toEqual([1, 2]);
  });

  it("Pagination mirrors its direction glyph under RTL", () => {
    const html = renderToStaticMarkup(
      <Pagination page={3} pageCount={9} onPageChange={() => {}} />,
    );
    expect(html).toContain("rtl:scale-x-[-1]");
  });

  it("Pager renders disabled edges around the middle slot", () => {
    const html = renderToStaticMarkup(
      <Pager prevDisabled nextAriaLabel="Next day">
        <PagerPage current>1</PagerPage>
        <PagerPage>2</PagerPage>
      </Pager>,
    );
    expect(html).toContain('data-slot="pager"');
    expect(html).toContain('data-slot="pager-page"');
    expect(html).toContain('aria-current="page"');
    expect(html).toContain('aria-label="Next day"');
    expect(html).toContain("disabled");
    expect(html).toContain("cursor-pointer");
  });

  it("Pager capsule dress reproduces the dashboard one-capsule look", () => {
    const html = renderToStaticMarkup(<Pager dress="capsule" nextAriaLabel="Next" />);
    expect(html).toContain("bg-term-bg");
    expect(html).toContain("grid-cols-[auto_1fr_auto]");
    expect(html).toContain("disabled:cursor-not-allowed");
  });

  it("DatePager renders the capsule label and calendar trigger", () => {
    const html = renderToStaticMarkup(
      <DatePager value="2026-09-30" onChange={() => {}} labelAriaLabel="Pick date" />,
    );
    expect(html).toContain('data-slot="date-pager"');
    expect(html).toContain('data-slot="date-pager-trigger"');
    expect(html).toContain('aria-label="Pick date"');
    expect(html).toContain(formatDatePagerLabel("2026-09-30"));
    expect(formatDatePagerLabel("2026-09-30")).toBe("Wed, Sep 30, 2026");
    expect(html).toContain("tabular-nums");
    expect(html).toContain("bg-term-bg");
  });

  it("DatePager mirrors its month/step chevrons under RTL", () => {
    const html = renderToStaticMarkup(<DatePager value="2026-09-30" onChange={() => {}} />);
    expect(html).toContain("rtl:scale-x-[-1]");
  });

  it("TagsInput renders chips with remove controls and filtered suggestions", () => {
    const html = renderToStaticMarkup(
      <TagsInput
        value={["momentum", "ETH-USD"]}
        placeholder="filter strategies…"
        suggestions={["momentum", "carry"]}
      />,
    );
    expect(html).toContain('data-slot="tags-input"');
    expect(html).toContain('data-slot="tag-chip"');
    expect(html).toContain('aria-label="Remove momentum"');
    // chips present → placeholder suppressed
    expect(html).not.toContain("filter strategies…");
    // already-added suggestion filtered, remaining rendered as +chip
    expect(html).toContain("+ carry");
    expect(html.match(/data-slot="tag-suggestions"/g)).toHaveLength(1);
  });

  it("TagsInput stretches the input while chipless and shows the placeholder", () => {
    const html = renderToStaticMarkup(<TagsInput value={[]} placeholder="filter strategies…" />);
    expect(html).toContain('placeholder="filter strategies…"');
    expect(html).toContain("first:flex-1");
    expect(html).not.toContain('data-slot="tag-chip"');
  });

  it("SearchBar shows the hint slot while empty and swaps it for clear on input", () => {
    const empty = renderToStaticMarkup(
      <SearchBar value="" onChange={() => {}} hint={<kbd className="kbd">/</kbd>} />,
    );
    expect(empty).toContain('data-slot="search-bar"');
    expect(empty).toContain("/");
    expect(empty).not.toContain('aria-label="Clear search"');

    const filled = renderToStaticMarkup(
      <SearchBar value="sharpe" onChange={() => {}} hint={<kbd className="kbd">/</kbd>} />,
    );
    expect(filled).toContain('aria-label="Clear search"');
    expect(filled).not.toContain("<kbd");
    expect(filled).toContain("webkit-search-cancel-button");
  });

  it("SearchBar and TagsInput carry pointer cursors on their controls", () => {
    const search = renderToStaticMarkup(<SearchBar value="x" onChange={() => {}} />);
    expect(search).toContain("cursor-pointer");
    const tags = renderToStaticMarkup(
      <TagsInput value={["a"]} suggestions={["b"]} onRemove={() => {}} />,
    );
    expect(tags).toContain("cursor-pointer");
  });

  it("Form and FormField wire label, hint and error into the control", () => {
    const html = renderToStaticMarkup(
      <Form>
        <FormField label="Ticker" hint="Lowercase.">
          <input name="ticker" />
        </FormField>
        <FormActions>
          <button type="button">Save</button>
        </FormActions>
      </Form>,
    );
    expect(html).toContain('data-slot="form"');
    expect(html).toContain('data-slot="field"');
    expect(html).toContain('data-slot="form-actions"');
    expect(html).toMatch(/<label[^>]*for="/);
    expect(html).toContain("Lowercase.");
    expect(html).toMatch(/aria-describedby="/);
  });

  it("Form marks required on the control and shows the required affordance", () => {
    const html = renderToStaticMarkup(
      <Form>
        <FormField label="Ticker" error="Required." required>
          <input name="ticker" />
        </FormField>
      </Form>,
    );
    expect(html).toContain("Required.");
    expect(html).toContain('aria-invalid="true"');
    expect(html).toContain("(required)");
  });

  it("Avatar composes root, image and fallback parts", () => {
    const html = renderToStaticMarkup(
      <div>
        <Avatar>
          <AvatarImage src="/brand/avatar/digithings-avatar-dark.png" alt="digithings" />
          <AvatarFallback>DG</AvatarFallback>
        </Avatar>
        <AvatarGroup>
          <Avatar size="sm">
            <AvatarFallback>dg</AvatarFallback>
            <AvatarBadge />
          </Avatar>
          <AvatarGroupCount>+5</AvatarGroupCount>
        </AvatarGroup>
      </div>,
    );
    expect(html).toContain('data-slot="avatar"');
    expect(html).toContain('data-slot="avatar-fallback"');
    expect(html).toContain('data-slot="avatar-group"');
    expect(html).toContain('data-slot="avatar-group-count"');
    expect(html).toContain('data-slot="avatar-badge"');
    expect(html).toContain('data-size="sm"');
    // the status badge anchors to the inline end, not the physical right
    expect(html).toContain("end-0");
    expect(html).not.toContain("right-0");
  });
});
