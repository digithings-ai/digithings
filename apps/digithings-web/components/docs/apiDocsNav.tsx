import type { DocsNavGroup } from "@digithings/ui";
import { OPENAPI_SERVICES } from "@/lib/openapiCatalog";

export function ServiceWordmark({ id }: { id: string }) {
  return (
    <>
      <span className="dt-d">digi</span>
      <span className="dt-s">{id.replace(/^digi/, "")}</span>
    </>
  );
}

/**
 * The OpenAPI pages' sidebar: page links, not in-page sections — one spine
 * from the guides through the explorer index to each service's spec, lit on
 * the page being read. `current` is the service id, or undefined on the index.
 */
export function apiDocsNav(current?: string): DocsNavGroup[] {
  return [
    {
      label: "Docs",
      items: [
        { id: "docs", label: "Guides & reference", href: "/docs/" },
        { id: "api", label: "OpenAPI explorer", href: "/docs/api/", current: current == null },
      ],
    },
    {
      label: "Services",
      items: OPENAPI_SERVICES.map((s) => ({
        id: `api-${s.id}`,
        label: <ServiceWordmark id={s.id} />,
        href: `/docs/api/${s.id}/`,
        current: s.id === current,
      })),
    },
  ];
}
