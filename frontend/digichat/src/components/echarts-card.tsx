"use client";

import { Component, type ReactNode, useEffect, useRef, useState } from "react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * ECharts chart card.
 *
 * - Takes a `spec` object (an ECharts `option`) and renders it in a responsive
 *   container via an echarts instance that is dynamically imported (no SSR,
 *   no bundle cost for non-chart conversations).
 * - On any render / import failure, falls back to a "Chart failed to render"
 *   card with a collapsible raw-JSON disclosure so the user is not left with
 *   a silent empty block.
 * - Supported chart types = whatever ECharts itself supports (bar, line,
 *   scatter, pie, etc.). The spec IS the ECharts option — no adapter layer.
 *
 * Security: the spec is JSON, never HTML. We do not pass custom formatters,
 * so ECharts option objects have no XSS surface here.
 */
export function EChartsCard({
  spec,
  className,
}: {
  spec: Record<string, unknown>;
  className?: string;
}) {
  return (
    <EChartsErrorBoundary spec={spec}>
      <EChartsRenderer spec={spec} className={className} />
    </EChartsErrorBoundary>
  );
}

function EChartsRenderer({
  spec,
  className,
}: {
  spec: Record<string, unknown>;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [renderError, setRenderError] = useState<Error | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let disposed = false;
    let chart: { setOption: (o: unknown) => void; resize: () => void; dispose: () => void } | null =
      null;
    const resizeObserver = new ResizeObserver(() => chart?.resize());

    (async () => {
      try {
        // Dynamic import keeps echarts out of the main bundle.
        const echarts = await import("echarts");
        if (disposed) return;
        chart = echarts.init(el);
        chart.setOption(spec);
        resizeObserver.observe(el);
      } catch (err) {
        if (!disposed) {
          setRenderError(err instanceof Error ? err : new Error(String(err)));
        }
      }
    })();

    return () => {
      disposed = true;
      resizeObserver.disconnect();
      chart?.dispose();
    };
  }, [spec]);

  if (renderError) {
    return <ChartFailedCard spec={spec} error={renderError} />;
  }

  return (
    <Card
      className={cn(
        "overflow-hidden border-border/40 bg-black/20 p-2",
        className,
      )}
    >
      <div
        ref={containerRef}
        data-testid="echarts-container"
        className="w-full"
        style={{ width: "100%", minHeight: 280, height: 320 }}
      />
    </Card>
  );
}

function ChartFailedCard({
  spec,
  error,
}: {
  spec: Record<string, unknown>;
  error: Error;
}) {
  return (
    <Card className="border-destructive/40 bg-destructive/10 p-3 text-sm">
      <p className="mb-2 text-destructive-foreground">
        Chart failed to render
        {error.message ? `: ${error.message}` : ""}
      </p>
      <Collapsible>
        <CollapsibleTrigger className="cursor-pointer text-xs text-muted-foreground underline-offset-2 hover:underline">
          View raw JSON
        </CollapsibleTrigger>
        <CollapsibleContent>
          <pre className="mt-2 max-h-64 overflow-auto rounded-md border border-border/40 bg-black/30 p-2 font-mono text-[11px]">
            {JSON.stringify(spec, null, 2)}
          </pre>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}

type BoundaryProps = { spec: Record<string, unknown>; children: ReactNode };
type BoundaryState = { error: Error | null };

class EChartsErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error };
  }

  render() {
    if (this.state.error) {
      return <ChartFailedCard spec={this.props.spec} error={this.state.error} />;
    }
    return this.props.children;
  }
}
