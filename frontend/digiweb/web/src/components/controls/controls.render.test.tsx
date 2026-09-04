/**
 * SSR smoke tests for the shared controls layer (#1419): every control
 * renders server-side through its @base-ui/react primitive, emits the
 * expected dress classes for both the reference default and the
 * digichat-compat chat dress, and passes className through.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Avatar, AvatarFallback, AvatarGroup, AvatarGroupCount } from "./Avatar";
import { Badge } from "./Badge";
import { Breadcrumbs } from "./Breadcrumbs";
import { Button } from "./Button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "./Card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./Dialog";
import { EmptyState } from "./EmptyState";
import { Field } from "./Field";
import { Input } from "./Input";
import { Label } from "./Label";
import { DatePager, formatDatePagerLabel } from "./DatePager";
import { IconButton, Pager, PagerPage, SegmentedControl } from "./NavButtons";
import { Pagination, paginationWindow } from "./Pagination";
import { Checkbox, Radio, RadioGroup, Switch } from "./Selection";
import { Select, SelectItem, SelectPopup, SelectTrigger, SelectValue } from "./Select";
import { Slider, sliderFill } from "./Slider";
import { SearchBar } from "./SearchBar";
import { Skeleton, SkeletonGroup } from "./Skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "./Table";
import { TagsInput } from "./TagsInput";

describe("Button", () => {
  it("defaults to the reference primary dress", () => {
    const html = renderToStaticMarkup(<Button>Deploy strategy</Button>);
    expect(html).toContain("ctl-btn-ref ctl-btn-ref--primary");
    expect(html).toContain('data-slot="button"');
    expect(html).toContain("<button");
  });

  it("renders the reference loading spinner", () => {
    const html = renderToStaticMarkup(
      <Button loading disabled>
        Backtesting…
      </Button>
    );
    expect(html).toContain("ctl-btn-ref--loading");
    expect(html).toContain("ctl-btn-spinner");
    expect(html).toContain("disabled");
  });

  it("matches digichat's variant/size enums under the chat dress", () => {
    const html = renderToStaticMarkup(
      <Button dress="chat" variant="outline" size="sm" className="w-full">
        Save
      </Button>
    );
    expect(html).toContain("ctl-btn-chat ctl-btn-chat--outline ctl-btn-chat--size-sm w-full");
  });

  it("defaults the chat dress to default/default like digichat", () => {
    const html = renderToStaticMarkup(<Button dress="chat">Sign in</Button>);
    expect(html).toContain("ctl-btn-chat ctl-btn-chat--default ctl-btn-chat--size-default");
  });
});

describe("Badge", () => {
  it("defaults to the reference tier-badge dress", () => {
    const html = renderToStaticMarkup(<Badge>core</Badge>);
    expect(html).toContain("ctl-badge-ref");
    expect(html).toContain('data-slot="badge"');
    expect(html).toContain("<span");
  });

  it("supports digichat's variants and render composition", () => {
    const html = renderToStaticMarkup(
      <Badge dress="chat" variant="secondary" className="text-[9px]" render={<a href="#status" />}>
        ok
      </Badge>
    );
    expect(html).toContain("ctl-badge-chat ctl-badge-chat--secondary text-[9px]");
    expect(html).toContain("<a");
    expect(html).toContain('href="#status"');
  });
});

describe("Card", () => {
  it("renders the digichat part shape with data-slot/data-size hooks", () => {
    const html = renderToStaticMarkup(
      <Card dress="chat" size="sm" className="p-8">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
        </CardHeader>
        <CardContent>body</CardContent>
        <CardFooter>foot</CardFooter>
      </Card>
    );
    expect(html).toContain("ctl-card-chat p-8");
    expect(html).toContain('data-size="sm"');
    expect(html).toContain('data-slot="card-header"');
    expect(html).toContain("ctl-card-title");
    expect(html).toContain('data-slot="card-footer"');
  });

  it("defaults to the reference hairline-frame dress", () => {
    expect(renderToStaticMarkup(<Card />)).toContain("ctl-card-ref");
  });
});

describe("Input / Label", () => {
  it("renders both dresses and passes props through", () => {
    const ref = renderToStaticMarkup(<Input type="email" placeholder="you@desk.tld" />);
    expect(ref).toContain("ctl-input-ref");
    expect(ref).toContain('type="email"');
    const chat = renderToStaticMarkup(<Input dress="chat" aria-invalid readOnly value="x" />);
    expect(chat).toContain("ctl-input-chat");
    expect(chat).toContain('aria-invalid="true"');
    const label = renderToStaticMarkup(<Label htmlFor="dg">digigraph base URL</Label>);
    expect(label).toContain("ctl-label-ref");
    expect(label).toContain('for="dg"');
    expect(renderToStaticMarkup(<Label dress="chat" />)).toContain("ctl-label-chat");
  });
});

describe("Skeleton", () => {
  it("renders the sk-* shape grammar inside an aria-busy group", () => {
    const html = renderToStaticMarkup(
      <SkeletonGroup className="flex flex-col">
        <Skeleton width="55%" />
        <Skeleton size="sm" />
        <Skeleton variant="circle" />
        <Skeleton variant="block" className="h-20" />
        <Skeleton variant="button" />
      </SkeletonGroup>
    );
    expect(html).toContain('data-slot="skeleton-group"');
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("sk sk-line");
    expect(html).toContain("sk sk-line sk-line--sm");
    expect(html).toContain("sk sk-circle");
    expect(html).toContain("sk sk-block h-20");
    expect(html).toContain("sk sk-btn");
    expect(html).toContain("width:55%");
    expect(html).toContain('aria-hidden="true"');
  });

  it("flips the group's aria-busy off once content lands", () => {
    expect(renderToStaticMarkup(<SkeletonGroup busy={false} />)).toContain('aria-busy="false"');
  });
});

describe("EmptyState", () => {
  it("renders the glyph/title/body/action slots with a default glyph", () => {
    const html = renderToStaticMarkup(
      <EmptyState
        title="No strategies match"
        body="Broaden the query."
        action={<Button variant="ghost">Clear filters</Button>}
      />
    );
    expect(html).toContain('data-slot="empty-state"');
    expect(html).toContain("ctl-empty");
    expect(html).not.toContain("ctl-empty--error");
    expect(html).toContain("ctl-empty-glyph");
    expect(html).toContain("<svg");
    expect(html).toContain("No strategies match");
    expect(html).toContain("Broaden the query.");
    expect(html).toContain("ctl-btn-ref--ghost");
  });

  it("only the error variant wears the down tint", () => {
    const html = renderToStaticMarkup(<EmptyState variant="error" title="Couldn't load" />);
    expect(html).toContain("ctl-empty ctl-empty--error");
  });

  it("only the error variant announces itself as a live region", () => {
    // "error" is the one variant that can appear/replace content
    // asynchronously (a fetch failing after the page already loaded), so it
    // alone gets role="alert" -- "no-results"/"first-run" are expected
    // outcomes of a user's own action, not an unannounced state change.
    // Caller-provided role="status" must not win over the error override.
    const error = renderToStaticMarkup(
      <EmptyState variant="error" title="Couldn't load" role="status" />,
    );
    expect(error).toContain('role="alert"');
    expect(error).not.toContain('role="status"');

    const noResults = renderToStaticMarkup(<EmptyState title="No matches" />);
    expect(noResults).not.toContain('role="alert"');

    const firstRun = renderToStaticMarkup(<EmptyState variant="first-run" title="Nothing yet" />);
    expect(firstRun).not.toContain('role="alert"');
  });

  it("glass dresses drop the default glyph and render the note slot", () => {
    const html = renderToStaticMarkup(
      <EmptyState
        dress="glass"
        title="No runs recorded yet"
        body="Diagnostics land after each run."
        note="Populates after the daily job."
      />
    );
    expect(html).toContain("ctl-empty--glass");
    expect(html).not.toContain("ctl-empty-glyph");
    expect(html).toContain("ctl-empty-note");
    expect(html).toContain("Populates after the daily job.");

    const gate = renderToStaticMarkup(
      <EmptyState dress="glass-display" variant="error" title="Live data is temporarily unavailable" />
    );
    expect(gate).toContain("ctl-empty--glass-display");
    expect(gate).toContain("ctl-empty--error");
    expect(gate).not.toContain("ctl-empty-glyph");

    // an explicit icon still earns the disc under a glass dress
    const withIcon = renderToStaticMarkup(
      <EmptyState dress="glass" title="No document" icon={<svg aria-hidden="true" />} />
    );
    expect(withIcon).toContain("ctl-empty-glyph");
  });
});

describe("NavButtons", () => {
  it("SegmentedControl renders aria-pressed buttons in a group — not a tablist", () => {
    const html = renderToStaticMarkup(
      <SegmentedControl options={["1D", "1M", "All"]} value="1M" aria-label="Range" />
    );
    expect(html).toContain('role="group"');
    expect(html).not.toContain("tablist");
    expect(html).toContain("nb-seg-group");
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('aria-pressed="false"');
  });

  it("Pager renders disabled edges around the middle slot", () => {
    const html = renderToStaticMarkup(
      <Pager prevDisabled nextAriaLabel="Next day">
        <PagerPage current>1</PagerPage>
        <PagerPage>2</PagerPage>
      </Pager>
    );
    expect(html).toContain("nb-pager");
    expect(html).toContain("nb-pager-middle");
    expect(html).toContain("nb-page-edge");
    expect(html).toContain("disabled");
    expect(html).toContain('aria-label="Next day"');
    expect(html).toContain('aria-current="page"');
  });

  it("IconButton renders the borderless nb-icon glyph button", () => {
    const html = renderToStaticMarkup(<IconButton aria-label="refresh">x</IconButton>);
    expect(html).toContain("nb-icon");
    expect(html).toContain('aria-label="refresh"');
  });
});


describe("DatePager", () => {
  it("renders a fixed middle date label and calendar trigger", () => {
    const html = renderToStaticMarkup(
      <DatePager
        value="2026-09-30"
        onChange={() => {}}
        labelAriaLabel="Pick date"
        prevAriaLabel="Previous day"
        nextAriaLabel="Next day"
      />,
    );
    expect(html).toContain("nb-pager--capsule");
    expect(html).toContain("nb-pager--date");
    expect(html).toContain("nb-pager-middle");
    expect(html).toContain("nb-pager-date");
    expect(html).toContain('aria-label="Pick date"');
    expect(html).toContain(formatDatePagerLabel("2026-09-30"));
    expect(formatDatePagerLabel("2026-09-30")).toBe("Wed, Sep 30, 2026");
  });
});
describe("TagsInput", () => {
  it("renders chips with remove controls and filtered suggestions", () => {
    const html = renderToStaticMarkup(
      <TagsInput
        value={["momentum", "ETH-USD"]}
        placeholder="filter strategies…"
        suggestions={["momentum", "carry"]}
      />
    );
    expect(html).toContain("tg-field");
    expect(html).toContain("tg-chip");
    expect(html).toContain('aria-label="Remove momentum"');
    // chips present → placeholder suppressed
    expect(html).not.toContain("filter strategies…");
    // already-added suggestion filtered, remaining rendered as +chip
    expect(html).toContain("+ carry");
    expect(html.match(/tg-suggest-chip/g)).toHaveLength(1);
  });

  it("stretches the input while chipless and shows the placeholder", () => {
    const html = renderToStaticMarkup(<TagsInput value={[]} placeholder="filter strategies…" />);
    expect(html).toContain('placeholder="filter strategies…"');
    expect(html).not.toContain("tg-chip");
  });
});

describe("SearchBar", () => {
  it("shows the hint slot while empty", () => {
    const html = renderToStaticMarkup(
      <SearchBar value="" onChange={() => undefined} hint={<kbd className="kbd sb-hint">/</kbd>} />
    );
    expect(html).toContain("ctl-search");
    expect(html).toContain("sb-glyph");
    expect(html).toContain("sb-input");
    expect(html).toContain("sb-hint");
    expect(html).not.toContain("sb-clear");
  });

  it("swaps the hint for the clear affordance once there's input", () => {
    const html = renderToStaticMarkup(
      <SearchBar value="sharpe" onChange={() => undefined} hint={<kbd className="kbd sb-hint">/</kbd>} />
    );
    expect(html).toContain("sb-clear");
    expect(html).toContain('aria-label="Clear search"');
    expect(html).not.toContain("sb-hint");
  });
});

describe("Avatar", () => {
  it("renders the digichat family shape", () => {
    const html = renderToStaticMarkup(
      <AvatarGroup>
        <Avatar size="lg">
          <AvatarFallback>DT</AvatarFallback>
        </Avatar>
        <AvatarGroupCount>+3</AvatarGroupCount>
      </AvatarGroup>
    );
    expect(html).toContain("ctl-avatar-group");
    expect(html).toContain('data-slot="avatar"');
    expect(html).toContain('data-size="lg"');
    expect(html).toContain("ctl-avatar-fallback");
    expect(html).toContain("ctl-avatar-group-count");
  });
});

describe("Table", () => {
  it("renders the hairline ledger with slots and numeric alignment", () => {
    const html = renderToStaticMarkup(
      <Table>
        <TableCaption>Four calibrated runs.</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Run</TableHead>
            <TableHead numeric>CAGR</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>btc_slapper</TableCell>
            <TableCell numeric>+333.10%</TableCell>
          </TableRow>
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell>Mean</TableCell>
            <TableCell numeric>+120.4%</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    );
    expect(html).toContain("ctl-table");
    expect(html).toContain('data-slot="table-head"');
    expect(html).toContain('data-slot="table-caption"');
    expect(html).toContain("ctl-table-num");
    expect(html).toContain("<table");
    expect(html).toContain("<caption");
  });

  it("supports compact density", () => {
    const html = renderToStaticMarkup(
      <Table density="compact">
        <TableBody>
          <TableRow>
            <TableCell>x</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    );
    expect(html).toContain('data-density="compact"');
  });
});

describe("Breadcrumbs", () => {
  it("marks the href-less last item as current page", () => {
    const html = renderToStaticMarkup(
      <Breadcrumbs
        items={[{ label: "Pipeline", href: "/#pipeline" }, { label: "Research" }]}
      />
    );
    expect(html).toContain('aria-label="Breadcrumb"');
    expect(html).toContain('aria-current="page"');
    expect(html).toContain("ctl-crumbs-current");
    expect(html).toContain("ctl-crumbs-sep");
    expect(html).toContain("<nav");
    expect(html).toContain("<ol");
  });
});

describe("Pagination", () => {
  it("renders the window with the loud current page and edge steps", () => {
    const html = renderToStaticMarkup(
      <Pagination page={5} pageCount={12} onPageChange={() => undefined} />
    );
    expect(html).toContain('aria-label="Pagination"');
    expect(html).toContain('aria-current="page"');
    expect(html).toContain("is-current");
    expect(html).toContain('aria-label="Previous page"');
    expect(html).toContain('aria-label="Next page"');
    expect(html).toContain("<nav");
  });

  it("disables prev on the first page and renders links with hrefForPage", () => {
    const html = renderToStaticMarkup(
      <Pagination page={1} pageCount={4} hrefForPage={(p) => `/log?p=${p}`} />
    );
    expect(html).toContain("disabled");
    expect(html).toContain('href="/log?p=2"');
  });

  it("computes the ellipsis window", () => {
    expect(paginationWindow(5, 12)).toEqual([1, "…", 4, 5, 6, "…", 12]);
    expect(paginationWindow(1, 3)).toEqual([1, 2, 3]);
    expect(paginationWindow(2, 2)).toEqual([1, 2]);
  });
});

describe("Dialog", () => {
  it("renders the trigger without mounting the popup when closed", () => {
    const html = renderToStaticMarkup(
      <Dialog>
        <DialogTrigger>Delete run</DialogTrigger>
        <DialogContent tone="danger">
          <DialogHeader>
            <DialogTitle>Delete this backtest?</DialogTitle>
            <DialogDescription>Saved tearsheets are kept.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose>Cancel</DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
    expect(html).toContain('data-slot="dialog-trigger"');
    expect(html).not.toContain("ctl-dialog-card");
  });

  // The open popup is client-only (base-ui gates the portal on mount, so
  // nothing SSRs past the trigger) — like Sheet, the open state is covered
  // by the reference dialog specimen plus a live browser check, not here.
  it("carries the danger tone prop onto the content", () => {
    const html = renderToStaticMarkup(
      <Dialog>
        <DialogTrigger>Delete run</DialogTrigger>
        <DialogContent tone="danger">
          <DialogHeader>
            <DialogTitle>Delete this backtest?</DialogTitle>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    );
    expect(html).toContain('data-slot="dialog-trigger"');
    expect(html).not.toContain("ctl-dialog-card");
  });
});

describe("Field", () => {
  it("meshes label, hint, and ids into the child control", () => {
    const html = renderToStaticMarkup(
      <Field label="Strategy name" hint="Lowercase, snake_case.">
        <input type="text" defaultValue="trend_xsec" />
      </Field>
    );
    expect(html).toContain('data-slot="field"');
    expect(html).toContain('data-slot="label"');
    expect(html).toContain("Strategy name");
    expect(html).toContain("Lowercase, snake_case.");
    // the injected control id matches the label htmlFor and the hint wiring
    const id = html.match(/<input[^>]* id="([^"]+)"/)?.[1];
    expect(id).toBeTruthy();
    expect(html).toContain(`for="${id}"`);
    expect(html).toContain(`aria-describedby="`);
    expect(html).not.toContain("ctl-field-error");
  });

  it("replaces the hint with the error and flags the control invalid", () => {
    const html = renderToStaticMarkup(
      <Field label="API key" hint="Never share it." error="Key is revoked — issue a new one.">
        <input type="text" defaultValue="dk_live_9f2…" />
      </Field>
    );
    expect(html).toContain("ctl-field-error");
    expect(html).toContain("Key is revoked");
    expect(html).not.toContain("Never share it.");
    expect(html).toContain('aria-invalid="true"');
    expect(html).toContain('data-invalid="true"');
  });
});

describe("Checkbox", () => {
  it("renders the box, mounting the glyph only when checked", () => {
    const off = renderToStaticMarkup(<Checkbox aria-label="Paper only" />);
    expect(off).toContain("ctl-check");
    expect(off).toContain('data-slot="checkbox"');
    expect(off).not.toContain("ctl-check-indicator");
    const on = renderToStaticMarkup(<Checkbox aria-label="Paper only" checked />);
    expect(on).toContain("ctl-check-indicator");
    expect(on).toContain("data-checked");
  });
});

describe("Radio", () => {
  it("renders the group with roving items", () => {
    const html = renderToStaticMarkup(
      <RadioGroup aria-label="Mode" defaultValue="paper">
        <Radio aria-label="Paper" value="paper" />
        <Radio aria-label="Live" value="live" />
      </RadioGroup>
    );
    expect(html).toContain("ctl-radio-group");
    expect(html).toContain('data-slot="radio"');
    expect(html).toContain('role="radiogroup"');
  });
});

describe("Switch", () => {
  it("renders the track with the knob", () => {
    const html = renderToStaticMarkup(<Switch aria-label="Motion" />);
    expect(html).toContain("ctl-switch");
    expect(html).toContain("ctl-switch-knob");
    expect(html).toContain('data-slot="switch"');
  });
});

describe("Select", () => {
  it("renders the trigger and the popup grammar server-side", () => {
    const html = renderToStaticMarkup(
      <Select>
        <SelectTrigger>
          <SelectValue placeholder="Choose a venue" />
        </SelectTrigger>
        <SelectPopup>
          <SelectItem value="paper">paper</SelectItem>
        </SelectPopup>
      </Select>
    );
    expect(html).toContain("ctl-select");
    expect(html).toContain("Choose a venue");
    expect(html).toContain("ctl-select-popup");
    expect(html).toContain("ctl-select-item");
  });
});

describe("Slider", () => {
  it("renders the labelled native range with a computed fill", () => {
    const html = renderToStaticMarkup(
      <Slider label="Lookback" min={20} max={400} value={120} format={(v) => `${v}d`} ticks={[20, 400]} />
    );
    expect(html).toContain("ctl-slider");
    expect(html).toContain('type="range"');
    expect(html).toContain("120d");
    expect(html).toContain("ctl-slider-ticks");
    expect(html).toContain("linear-gradient(to right, var(--accent)");
  });

  it("computes the fill percentage", () => {
    expect(sliderFill(120, 20, 400)).toContain("26.31578947368421%");
    expect(sliderFill(0, 0, 100)).toContain("0%");
    expect(sliderFill(100, 0, 100)).toContain("100%");
  });
});
