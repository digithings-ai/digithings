'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { usePathname } from 'next/navigation';
import { Breadcrumbs, type Crumb } from '@digithings/ui/ui';
import { AsOfBadge } from '@/components/shared/as-of-badge';
import { useDashboard } from '@/lib/dashboard-context';
import { dashboardBasePath } from '@/lib/supabase';
import { destinationFor, layoutFor, normalizePath, titleFor, type LayoutMode } from './nav-model';

export interface PageHeaderSpec {
  title?: string;
  crumbs?: Crumb[];
  /** Overrides the default as-of date (portfolio meta). `null` hides the badge. */
  asOf?: string | null;
  actions?: ReactNode;
  layout?: LayoutMode;
}

type Ctx = {
  spec: PageHeaderSpec;
  setSpec: (spec: PageHeaderSpec | null) => void;
};

const PageHeaderContext = createContext<Ctx | null>(null);

export function PageHeaderProvider({ children }: { children: ReactNode }) {
  const [spec, setSpecState] = useState<PageHeaderSpec>({});
  // setSpec must keep one identity: usePageHeader lists it as an effect dep, so a
  // per-spec setter re-runs that effect on every registration and never settles.
  const setSpec = useCallback((s: PageHeaderSpec | null) => setSpecState(s ?? {}), []);
  const value = useMemo<Ctx>(() => ({ spec, setSpec }), [spec, setSpec]);
  return <PageHeaderContext.Provider value={value}>{children}</PageHeaderContext.Provider>;
}

/**
 * A page describes its header band here: title, crumbs, as-of and toolbar.
 * Registered in an effect and cleared on unmount, so the shell's static
 * per-route title stays in the prerendered HTML until a page overrides it.
 */
export function usePageHeader(spec: PageHeaderSpec) {
  const ctx = useContext(PageHeaderContext);
  const setSpec = ctx?.setSpec;
  const { title, crumbs, asOf, actions, layout } = spec;
  useEffect(() => {
    setSpec?.({ title, crumbs, asOf, actions, layout });
    return () => setSpec?.(null);
  }, [setSpec, title, crumbs, asOf, actions, layout]);
}

/** Layout mode for the current route: page override, else the nav registry default. */
export function usePageLayout(): LayoutMode {
  const pathname = usePathname();
  const ctx = useContext(PageHeaderContext);
  return ctx?.spec.layout ?? layoutFor(pathname, dashboardBasePath());
}

export function PageHeader() {
  const pathname = usePathname();
  const ctx = useContext(PageHeaderContext);
  const { data } = useDashboard();
  const spec = ctx?.spec ?? {};
  const path = normalizePath(pathname, dashboardBasePath());
  const dest = destinationFor(path);
  const title = spec.title ?? titleFor(pathname, dashboardBasePath());
  const crumbs: Crumb[] =
    spec.crumbs ?? (dest && dest.href !== '/' && dest.title !== title ? [{ label: dest.label, href: dest.href }] : []);
  const meta = data?.portfolio?.meta ?? null;
  const asOf = spec.asOf === undefined ? (meta?.last_updated ?? null) : spec.asOf;

  // The sidebar already shows where you are, so the band only renders when a page
  // registers a toolbar or crumbs. The h1 stays (sr-only) for a11y and static prerender.
  if (!spec.actions && !spec.crumbs) return <h1 className="sr-only">{title}</h1>;

  return (
    <header
      data-print-hide
      className="flex min-h-10 shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-hair bg-surface px-4 py-1 md:px-6"
    >
      <div className="flex min-w-0 items-baseline gap-3">
        {crumbs.length > 0 ? (
          <>
            <Breadcrumbs items={crumbs} />
            <span aria-hidden className="text-ink-mute">
              /
            </span>
          </>
        ) : null}
        <h1 className="truncate font-mono text-sm text-ink">{title}</h1>
      </div>
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
        {asOf ? <AsOfBadge date={asOf} createdAt={meta?.last_run_at ?? null} /> : null}
        {spec.actions}
      </div>
    </header>
  );
}
