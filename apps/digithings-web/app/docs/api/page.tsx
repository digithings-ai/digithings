import type { Metadata } from "next";
import Link from "next/link";
import { DocsLayout } from "@digithings/ui";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";
import { ServiceWordmark, apiDocsNav } from "@/components/docs/apiDocsNav";
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
        <DocsLayout
          nav={apiDocsNav()}
          ariaLabel="api docs"
          hero={{
            kicker: "// openapi",
            title: "OpenAPI explorer.",
            lede: (
              <>
                Machine-readable contracts for every HTTP surface. Source of truth is the committed
                JSON under <code className="dc-code-inline">docs/openapi/</code> (regenerate with{" "}
                <code className="dc-code-inline">make openapi-export</code>). Product guides and the
                curated module reference stay on{" "}
                <Link className="doc-inline-link" href="/docs/">
                  /docs
                </Link>
                .
              </>
            ),
          }}
        >
          <ul className="m-0 list-none p-0 flex flex-col gap-[0.55rem]">
            {OPENAPI_SERVICES.map((s) => (
              <li key={s.id}>
                <Link
                  href={`/docs/api/${s.id}/`}
                  className="flex flex-col gap-[0.2rem] rounded-none border border-hair px-[1rem] py-[0.85rem] no-underline transition-colors duration-150 ease-brand hover:bg-accent-weak"
                >
                  <span className="font-mono text-[0.95rem] text-ink">
                    <ServiceWordmark id={s.id} />
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
        </DocsLayout>
      </main>
      <DtFooter />
    </>
  );
}
