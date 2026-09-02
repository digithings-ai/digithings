import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Footer } from "@digithings/web";
import { DT_FOOTER, DT_FOOTER_META } from "../../../_nav";
import { DtNav } from "@/components/DtNav";
import { SwaggerExplorer } from "@/components/docs/SwaggerExplorer";
import {
  OPENAPI_SERVICE_IDS,
  OPENAPI_SERVICES,
  openApiSpecPath,
  type OpenApiService,
} from "@/lib/openapiCatalog";

type Params = { service: string };

export function generateStaticParams(): Params[] {
  return OPENAPI_SERVICE_IDS.map((service) => ({ service }));
}

export function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  return params.then(({ service }) => {
    const entry = OPENAPI_SERVICES.find((s) => s.id === service);
    if (!entry) return { title: "API" };
    return {
      title: `${entry.id} — OpenAPI`,
      description: `OpenAPI reference for ${entry.id}: ${entry.role}`,
    };
  });
}

function ServiceWordmark({ id }: { id: string }) {
  return (
    <>
      <span className="dt-d">digi</span>
      <span className="dt-s">{id.replace(/^digi/, "")}</span>
    </>
  );
}

export default async function OpenApiServicePage({
  params,
}: {
  params: Promise<Params>;
}) {
  const { service } = await params;
  const entry: OpenApiService | undefined = OPENAPI_SERVICES.find((s) => s.id === service);
  if (!entry) notFound();

  return (
    <>
      <DtNav />
      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)] pb-[clamp(2rem,5vw,4rem)]">
        <div className="docs-shell docs-shell--wide">
          <div className="docs-content flex min-w-0 flex-col gap-[clamp(1.2rem,2.5vw,1.8rem)]">
            <nav className="flex flex-wrap items-center gap-[0.55rem] font-mono text-[0.72rem] text-ink-mute">
              <Link className="doc-inline-link" href="/docs/">
                docs
              </Link>
              <span aria-hidden="true">/</span>
              <Link className="doc-inline-link" href="/docs/api/">
                api
              </Link>
              <span aria-hidden="true">/</span>
              <span className="text-ink">{entry.id}</span>
            </nav>

            <header className="docs-hero">
              <p className="m-0 font-mono text-[0.68rem] uppercase tracking-[0.14em] text-accent">
                {"// openapi"}
              </p>
              <h1 className="mb-[0.55rem] mt-[0.45rem] font-display text-[clamp(1.7rem,3.5vw,2.4rem)] font-normal tracking-[-0.02em] text-ink">
                <ServiceWordmark id={entry.id} />
              </h1>
              <p className="m-0 max-w-[62ch] leading-[1.55] text-ink-soft">{entry.role}</p>
              <p className="m-0 mt-[0.65rem] text-[0.8rem] text-ink-mute">
                Spec:{" "}
                <a className="doc-inline-link" href={openApiSpecPath(entry.id)}>
                  {openApiSpecPath(entry.id)}
                </a>
                {entry.authored ? " · authored BFF contract" : " · FastAPI export via make openapi-export"}
                . Try-it-out is off on this public site — point clients at your own deployment.
              </p>
            </header>

            <nav
              className="flex flex-wrap gap-[0.45rem]"
              aria-label="OpenAPI services"
            >
              {OPENAPI_SERVICES.map((s) => (
                <Link
                  key={s.id}
                  href={`/docs/api/${s.id}/`}
                  aria-current={s.id === entry.id ? "page" : undefined}
                  className={`rounded-none border px-[0.65rem] py-[0.28rem] font-mono text-[0.76rem] no-underline transition-colors duration-150 ease-brand ${
                    s.id === entry.id
                      ? "border-accent bg-accent-weak text-ink"
                      : "border-hair text-ink-soft hover:bg-accent-weak hover:text-ink"
                  }`}
                >
                  <ServiceWordmark id={s.id} />
                </Link>
              ))}
            </nav>

            <SwaggerExplorer serviceId={entry.id} />
          </div>
        </div>
      </main>
      <Footer links={DT_FOOTER} meta={DT_FOOTER_META} />
    </>
  );
}
