"use client";

import { useEffect, useRef, useState } from "react";
import { openApiSpecPath } from "@/lib/openapiCatalog";

declare global {
  interface Window {
    SwaggerUIBundle?: {
      (opts: Record<string, unknown>): unknown;
      presets: { apis: unknown };
    };
    SwaggerUIStandalonePreset?: unknown;
  }
}

function loadStylesheet(href: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`link[data-swagger-href="${href}"]`);
    if (existing) {
      resolve();
      return;
    }
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    link.dataset.swaggerHref = href;
    link.onload = () => resolve();
    link.onerror = () => reject(new Error(`Failed to load ${href}`));
    document.head.appendChild(link);
  });
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-swagger-src="${src}"]`);
    if (existing) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.dataset.swaggerSrc = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.body.appendChild(script);
  });
}

/**
 * Embed Swagger UI against a same-origin OpenAPI JSON path.
 * Assets are vendored under /swagger-ui/ at prebuild (no CDN).
 */
export function SwaggerExplorer({ serviceId }: { serviceId: string }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const mount = hostRef.current;
    if (!mount) return;

    (async () => {
      try {
        await loadStylesheet("/swagger-ui/swagger-ui.css");
        await loadScript("/swagger-ui/swagger-ui-bundle.js");
        await loadScript("/swagger-ui/swagger-ui-standalone-preset.js");
        if (cancelled || !hostRef.current) return;
        const Bundle = window.SwaggerUIBundle;
        const Standalone = window.SwaggerUIStandalonePreset;
        if (!Bundle || !Standalone) {
          throw new Error("Swagger UI failed to initialize");
        }
        hostRef.current.innerHTML = "";
        const el = document.createElement("div");
        el.id = `swagger-ui-${serviceId}`;
        hostRef.current.appendChild(el);
        Bundle({
          url: openApiSpecPath(serviceId),
          dom_id: `#swagger-ui-${serviceId}`,
          presets: [Bundle.presets.apis, Standalone],
          layout: "BaseLayout",
          deepLinking: true,
          tryItOutEnabled: false,
          supportedSubmitMethods: [],
          validatorUrl: null,
          defaultModelsExpandDepth: 1,
          defaultModelExpandDepth: 1,
        });
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load OpenAPI explorer");
        }
      }
    })();

    return () => {
      cancelled = true;
      if (mount) mount.innerHTML = "";
    };
  }, [serviceId]);

  if (error) {
    return (
      <p className="m-0 text-[0.9rem] text-danger" role="alert">
        {error}. Spec still available at{" "}
        <a className="doc-inline-link" href={openApiSpecPath(serviceId)}>
          {openApiSpecPath(serviceId)}
        </a>
        .
      </p>
    );
  }

  return (
    <div
      ref={hostRef}
      className="docs-swagger"
      aria-label={`${serviceId} OpenAPI`}
      // Swagger UI injects its own markup; keep a min height so layout doesn't jump.
      style={{ minHeight: "24rem" }}
    />
  );
}
