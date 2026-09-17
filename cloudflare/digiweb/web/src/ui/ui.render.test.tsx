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
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectItemIndicator,
  SelectPopup,
  SelectTrigger,
  SelectValue,
  Separator,
  Sheet,
  SheetContent,
  SheetTrigger,
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

  it("Table numeric cells right-align with tabular figures", () => {
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
    expect(html).toContain("text-right tabular-nums");
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

  it("SelectPopup composes items inline and SelectItemIndicator renders its check", () => {
    const html = renderToStaticMarkup(
      <Select defaultValue="aapl" defaultOpen>
        <SelectTrigger>
          <SelectValue placeholder="Ticker" />
        </SelectTrigger>
        <SelectPopup>
          <SelectItem value="aapl">
            AAPL
            <SelectItemIndicator />
          </SelectItem>
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
    expect(html).toContain('data-slot="select-item-indicator"');
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
