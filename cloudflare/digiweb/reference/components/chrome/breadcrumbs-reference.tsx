/**
 * Breadcrumbs specimen — the wayfinding trail from @digithings/web, live.
 * Items are `{ label, href }`; the last item without an `href` renders as
 * the current page (`aria-current="page"`, not a link). Separators are
 * `/`, aria-hidden. Dress is `.ctl-crumbs*` in the package core sheet.
 */
import { Breadcrumbs } from "@digithings/web";

export function BreadcrumbsReference() {
  return (
    <section className="section-block" id="breadcrumbs">
      <p className="kicker">{"// breadcrumbs"}</p>
      <h2 className="title">You are here, in words.</h2>
      <p className="section-copy">
        <code>Breadcrumbs</code> from <code>@digithings/web</code> is the trail above a deep
        surface: every ancestor a link, the current page plain text. The separator is a slash,
        never a chevron — chevrons point, slashes locate.
      </p>

      <div className="mt-[1.2rem] flex flex-col gap-[0.9rem]">
        <Breadcrumbs
          items={[
            { label: "digiquant", href: "#breadcrumbs" },
            { label: "pipeline", href: "#breadcrumbs" },
            { label: "research" },
          ]}
        />
        <Breadcrumbs
          ariaLabel="Deep trail"
          items={[
            { label: "strategies", href: "#breadcrumbs" },
            { label: "btc_slapper", href: "#breadcrumbs" },
            { label: "trade log" },
          ]}
        />
      </div>
    </section>
  );
}
