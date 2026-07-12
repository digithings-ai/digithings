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
import { Input } from "./Input";
import { Label } from "./Label";

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
