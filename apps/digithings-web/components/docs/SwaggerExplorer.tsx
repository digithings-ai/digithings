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

/**
 * Load one vendored Swagger asset.
 *
 * An existing tag is not a finished load. A failed tag stays in the document
 * after `error`, and treating it as ready makes the next mount resolve before
 * `SwaggerUIBundle` exists — the explorer then stays broken until a full reload.
 * `ready` reuses the tag. `loading` waits on it. Anything else is removed and
 * fetched again.
 */
export function loadSwaggerAsset(
  kind: "script" | "stylesheet",
  url: string,
  doc: Document = document,
): Promise<void> {
  const isScript = kind === "script";
  const attr = isScript ? "data-swagger-src" : "data-swagger-href";
  const selector = `${isScript ? "script" : "link"}[${attr}="${url}"]`;

  return new Promise((resolve, reject) => {
    const fail = (node: Element) => {
      node.remove();
      reject(new Error(`Failed to load ${url}`));
    };
    const existing = doc.querySelector(selector);
    if (existing) {
      const status = existing.getAttribute("data-swagger-status");
      if (status === "ready") {
        resolve();
        return;
      }
      if (status === "loading") {
        existing.addEventListener("load", () => resolve(), { once: true });
        existing.addEventListener("error", () => fail(existing), { once: true });
        return;
      }
      existing.remove();
    }

    const node = isScript ? doc.createElement("script") : doc.createElement("link");
    node.setAttribute(attr, url);
    node.setAttribute("data-swagger-status", "loading");
    node.addEventListener("load", () => {
      node.setAttribute("data-swagger-status", "ready");
      resolve();
    });
    node.addEventListener("error", () => {
      node.setAttribute("data-swagger-status", "error");
      fail(node);
    });
    if (node instanceof HTMLScriptElement) {
      node.src = url;
      node.async = true;
      doc.body.appendChild(node);
      return;
    }
    if (node instanceof HTMLLinkElement) {
      node.rel = "stylesheet";
      node.href = url;
      doc.head.appendChild(node);
    }
  });
}

/**
 * Embed Swagger UI against a same-origin OpenAPI JSON path.
 * Assets are vendored under /swagger-ui/ at prebuild (no CDN).
 */
export function SwaggerExplorer({ serviceId }: { serviceId: string }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const mount = hostRef.current;
    if (!mount) return;

    (async () => {
      try {
        await loadSwaggerAsset("stylesheet", "/swagger-ui/swagger-ui.css");
        await loadSwaggerAsset("script", "/swagger-ui/swagger-ui-bundle.js");
        await loadSwaggerAsset("script", "/swagger-ui/swagger-ui-standalone-preset.js");
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
  }, [serviceId, attempt]);

  return (
    <div>
      {error ? (
        <p className="m-0 text-[0.9rem] text-danger" role="alert">
          {error}.{" "}
          <button
            type="button"
            className="doc-inline-link"
            onClick={() => {
              setError(null);
              setAttempt((n) => n + 1);
            }}
          >
            Try again
          </button>
          . Spec still available at{" "}
          <a className="doc-inline-link" href={openApiSpecPath(serviceId)}>
            {openApiSpecPath(serviceId)}
          </a>
          .
        </p>
      ) : null}
      <div
        ref={hostRef}
        className="docs-swagger"
        hidden={error != null}
        aria-label={`${serviceId} OpenAPI`}
        // Swagger UI injects its own markup; keep a min height so layout doesn't jump.
        style={{ minHeight: "24rem" }}
      />
    </div>
  );
}
