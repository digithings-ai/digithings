import type { Metadata } from "next";
import Link from "next/link";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";
import { OPENAPI_SERVICES } from "@/lib/openapiCatalog";

export const metadata: Metadata = {
  title: "API — OpenAPI explorer",
  description:
    "Interactive OpenAPI reference for digithings HTTP services. Specs are committed under " +
    "docs/openapi/ and served statically — not live FastAPI /docs on localhost.",
};

export default function OpenApiIndexPage() {
  return (
    <>
      <DtNav />
      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)] pb-[clamp(2rem,5vw,4rem)]">
        <div className="docs-shell">
          <div className="docs-content flex min-w-0 flex-col gap-[clamp(1.4rem,3vw,2.2rem)]">
            <header className="docs-hero">
              <p className="m-0 font-mono text-[0.68rem] uppercase tracking-[0.14em] text-accent">
                {"// openapi"}
              </p>
              <h1 className="mb-[0.7rem] mt-[0.5rem] font-display text-[clamp(1.9rem,4vw,2.7rem)] font-normal tracking-[-0.02em] text-ink">
                OpenAPI explorer.
              </h1>
              <p className="m-0 max-w-[60ch] leading-[1.6] text-ink-soft">
                Machine-readable contracts for every HTTP surface. Source of truth is the committed
                JSON under <code className="dc-code-inline">docs/openapi/</code> (regenerate with{" "}
                <code className="dc-code-inline">make openapi-export</code>). Product guides and the
                curated module reference stay on{" "}
                <Link className="doc-inline-link" href="/docs/">
                  /docs
                </Link>
                .
              </p>
            </header>

            <ul className="m-0 list-none p-0 flex flex-col gap-[0.55rem]">
              {OPENAPI_SERVICES.map((s) => (
                <li key={s.id}>
                  <Link
                    href={`/docs/api/${s.id}/`}
                    className="flex flex-col gap-[0.2rem] rounded-none border border-hair px-[1rem] py-[0.85rem] no-underline transition-colors duration-150 ease-brand hover:bg-accent-weak"
                  >
                    <span className="font-mono text-[0.95rem] text-ink">
                      <span className="dt-d">digi</span>
                      <span className="dt-s">{s.id.replace(/^digi/, "")}</span>
                      {s.port != null && (
                        <span className="ml-[0.55rem] text-[0.72rem] text-ink-mute">:{s.port}</span>
                      )}
                      {s.authored && (
                        <span className="ml-[0.55rem] text-[0.68rem] uppercase tracking-[0.1em] text-ink-mute">
                          authored
                        </span>
                      )}
                    </span>
                    <span className="text-[0.84rem] leading-[1.45] text-ink-soft">{s.role}</span>
                  </Link>
                </li>
              ))}
            </ul>

            <p className="m-0 text-[0.82rem] leading-[1.55] text-ink-mute">
              Raw JSON is also published at{" "}
              <code className="dc-code-inline">/openapi/&lt;service&gt;.json</code> after each site
              build. Local FastAPI Swagger at <code className="dc-code-inline">:port/docs</code>{" "}
              remains for operators with the stack up — it is not the public source of truth.
            </p>
          </div>
        </div>
      </main>
      <DtFooter />
    </>
  );
}
