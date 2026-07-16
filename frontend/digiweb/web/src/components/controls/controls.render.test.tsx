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
import { Button } from "./Button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "./Card";
import { EmptyState } from "./EmptyState";
import { Input } from "./Input";
import { Label } from "./Label";
import { IconButton, Pager, PagerPage, SegmentedControl } from "./NavButtons";
import { SearchBar } from "./SearchBar";
import { Skeleton, SkeletonGroup } from "./Skeleton";
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
  it("defaults to the reference tier-pill dress", () => {
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
    const label = renderToStaticMarkup(<Label htmlFor="dg">DigiGraph base URL</Label>);
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
