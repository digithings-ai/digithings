import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DocsLayout } from "@digithings/ui";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";
import { ServiceWordmark, apiDocsNav } from "@/components/docs/apiDocsNav";
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
        <DocsLayout
          nav={apiDocsNav(entry.id)}
          ariaLabel="api docs"
          hero={{
            kicker: "// openapi",
            title: <ServiceWordmark id={entry.id} />,
            lede: entry.role,
            actions: (
              <p className="m-0 text-[0.8rem] text-ink-mute">
                Spec:{" "}
                <a className="doc-inline-link" href={openApiSpecPath(entry.id)}>
                  {openApiSpecPath(entry.id)}
                </a>
                {entry.authored ? " · authored BFF contract" : " · FastAPI export via make openapi-export"}
                . Try-it-out is off on this public site — point clients at your own deployment.
              </p>
            ),
          }}
        >
          <SwaggerExplorer serviceId={entry.id} />
        </DocsLayout>
      </main>
      <DtFooter />
    </>
  );
}
