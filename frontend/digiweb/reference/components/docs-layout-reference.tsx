/**
 * Docs layout — the shared @digithings/web docs family in one contained
 * specimen: the sticky scroll-spied sidebar (a native <details> disclosure
 * below 860px — the sidebar never just vanishes, canon §17), endpoint chrome
 * with theme-aware HTTP-method chips, and label-tabbed code samples with a
 * hover-revealed copy button. Everything below is an invented "ordersvc" API —
 * illustrative only, badged as such. Static display template plus the family's
 * own client interactivity (tabs, copy, scroll-spy).
 */
import type { CSSProperties } from "react";
import {
  DocsCodeBlock,
  DocsLayout,
  EndpointDoc,
  MethodBadge,
  type DocsEndpoint,
  type DocsNavGroup,
} from "@digithings/web";

const NAV: DocsNavGroup[] = [
  {
    label: "Guides",
    items: [
      { id: "docs-demo-start", label: "Getting started" },
      { id: "docs-demo-auth", label: "Authentication" },
    ],
  },
  {
    label: "API",
    items: [
      { id: "docs-demo-methods", label: "Methods" },
      { id: "docs-demo-orders", label: "Orders" },
    ],
  },
];

const GET_ORDER: DocsEndpoint = {
  method: "GET",
  path: "/v1/orders/{id}",
  summary: "Fetch one order with its current lifecycle state and fill history.",
  auth: "orders:read",
  rateLimit: "60/min/key",
  responseFields: [
    { name: "id", type: "string", description: "Order id, e.g. ord_8f2c." },
    { name: "status", type: "enum", description: "accepted · working · filled · cancelled." },
    { name: "filled_qty", type: "number", description: "Cumulative filled quantity." },
  ],
  examples: [
    {
      label: "curl",
      code: 'curl $ORDERSVC_URL/v1/orders/ord_8f2c \\\n  -H "Authorization: Bearer $ORDERSVC_KEY"',
    },
    {
      label: "Python",
      code: 'order = client.orders.get("ord_8f2c")\nprint(order.status, order.filled_qty)',
    },
    {
      label: "TypeScript",
      code: 'const order = await client.orders.get("ord_8f2c");\nconsole.log(order.status, order.filledQty);',
    },
  ],
};

const POST_ORDER: DocsEndpoint = {
  method: "POST",
  path: "/v1/orders",
  summary: "Submit a new order. Rejected synchronously when a risk limit would be breached.",
  auth: "orders:write",
  flag: "ORDERSVC_ENABLE_TRADING=1",
  request: [
    { name: "symbol", type: "string", required: true, description: "Instrument, e.g. BTC-PERP." },
    { name: "side", type: "enum", required: true, description: "buy or sell." },
    { name: "qty", type: "number", required: true, description: "Order quantity, base units." },
    { name: "limit_px", type: "number", description: "Limit price; omit for market." },
  ],
  responseExample: '{\n  "id": "ord_8f2c",\n  "status": "accepted",\n  "filled_qty": 0\n}',
};

export function DocsLayoutReference() {
  return (
    <section className="section-block" id="docs-layout">
      <p className="kicker">{"// docs layout"}</p>
      <h2 className="title">Docs, with a spine.</h2>
      <p className="section-copy">
        The shared documentation family from <code>@digithings/web</code>: a sticky sidebar that
        scroll-spies the content on desktop and collapses into a native <code>details</code>{" "}
        disclosure on mobile, endpoint cards with method chips, field tables, and label-tabbed
        code samples whose copy button reveals on hover. The method chips consume the family&apos;s{" "}
        <code>var(--method-*)</code> custom props — each hue mixed 20% toward the theme&apos;s ink,
        so one rule stays legible on both themes.
      </p>
      <p className="mt-[0.9rem] inline-block rounded-full border border-hair px-[0.6rem] py-[0.15rem] font-mono text-[0.58rem] uppercase tracking-[0.08em] text-ink-mute">
        Example data · not live
      </p>

      <div
        className="mt-[1.4rem] rounded-[14px] border border-hair bg-surface/40 py-[clamp(1.2rem,3vw,2rem)]"
        style={{ "--docs-nav-h": "var(--nav-h)" } as CSSProperties}
      >
        <DocsLayout
          nav={NAV}
          ariaLabel="ordersvc docs"
          hero={{
            kicker: "// api docs",
            title: "ordersvc API reference.",
            lede:
              "Setup, authentication, and every endpoint with request/response schemas and runnable examples.",
          }}
        >
          <section
            id="docs-demo-start"
            className="flex flex-col gap-[0.6rem] border-t border-hair pt-[clamp(1.2rem,3vw,1.8rem)]"
          >
            <h2 className="m-0 font-display text-[clamp(1.4rem,2.6vw,1.9rem)] font-normal tracking-[-0.01em] text-ink">
              Getting started
            </h2>
            <p className="m-0 text-[0.88rem] leading-[1.65] text-ink-soft">
              Run the service locally and point the client at it. The compose file carries the
              canonical port.
            </p>
            <DocsCodeBlock code={"docker compose up -d ordersvc\nexport ORDERSVC_URL=http://localhost:8010"} />
          </section>

          <section
            id="docs-demo-auth"
            className="flex flex-col gap-[0.6rem] border-t border-hair pt-[clamp(1.2rem,3vw,1.8rem)]"
          >
            <h2 className="m-0 font-display text-[clamp(1.4rem,2.6vw,1.9rem)] font-normal tracking-[-0.01em] text-ink">
              Authentication
            </h2>
            <p className="m-0 text-[0.88rem] leading-[1.65] text-ink-soft">
              Every call carries a bearer key scoped to <code>orders:read</code> or{" "}
              <code>orders:write</code>. Keys are issued per environment and never cross paper and
              live.
            </p>
          </section>

          <section
            id="docs-demo-methods"
            className="flex flex-col gap-[0.6rem] border-t border-hair pt-[clamp(1.2rem,3vw,1.8rem)]"
          >
            <h3 className="m-0 font-mono text-[0.72rem] font-medium uppercase tracking-[0.14em] text-ink-mute">
              Method ramp
            </h3>
            <p className="m-0 text-[0.88rem] leading-[1.65] text-ink-soft">
              The four chips, one theme-aware ramp — GET steel, POST green, PUT amber, DELETE
              terracotta.
            </p>
            <div className="flex flex-wrap gap-[0.45rem]">
              <MethodBadge method="GET" />
              <MethodBadge method="POST" />
              <MethodBadge method="PUT" />
              <MethodBadge method="DELETE" />
            </div>
          </section>

          <section
            id="docs-demo-orders"
            className="flex flex-col gap-[1rem] border-t border-hair pt-[clamp(1.2rem,3vw,1.8rem)]"
          >
            <h3 className="m-0 font-mono text-[0.72rem] font-medium uppercase tracking-[0.14em] text-ink-mute">
              Endpoints
            </h3>
            <EndpointDoc ep={GET_ORDER} />
            <EndpointDoc ep={POST_ORDER} />
          </section>
        </DocsLayout>
      </div>
    </section>
  );
}
