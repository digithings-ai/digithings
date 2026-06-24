'use client';

import { Suspense, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import AtlasLoader from '@/components/AtlasLoader';
import { buildPipelineHref, stageForDocumentKey } from '@/lib/pipeline-links';

function RedirectFallback() {
  return <AtlasLoader fullScreen={false} />;
}

/** Old `/library` URLs → Pipeline node (preserve date/docKey when present). */
function LibraryToWhyInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const date = searchParams.get('date');
    const docKey = searchParams.get('docKey');
    router.replace(
      buildPipelineHref({
        date,
        node: docKey,
        stage: docKey ? stageForDocumentKey(docKey) ?? undefined : undefined,
      })
    );
  }, [router, searchParams]);

  return <RedirectFallback />;
}

export function LibraryToWhyRedirectPage() {
  return (
    <Suspense fallback={<RedirectFallback />}>
      <LibraryToWhyInner />
    </Suspense>
  );
}

/** Old `/strategy` URLs → Theses hub or thesis detail (optional thesis deep link). */
function StrategyToAnalysisInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const thesis = searchParams.get('thesis');
    if (thesis) {
      router.replace(`/portfolio/theses/${encodeURIComponent(thesis)}`);
      return;
    }
    router.replace('/portfolio?tab=theses');
  }, [router, searchParams]);

  return <RedirectFallback />;
}

export function StrategyToAnalysisRedirectPage() {
  return (
    <Suspense fallback={<RedirectFallback />}>
      <StrategyToAnalysisInner />
    </Suspense>
  );
}

/** Old `/performance` URL → Portfolio performance tab. */
export function PerformanceToPortfolioRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/portfolio?tab=performance');
  }, [router]);

  return <RedirectFallback />;
}

/** Old `/research` URL → Pipeline (route rename; preserve a date param when present). */
function ResearchToWhyInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const date = searchParams.get('date');
    router.replace(buildPipelineHref({ date }));
  }, [router, searchParams]);

  return <RedirectFallback />;
}

export function ResearchToWhyRedirectPage() {
  return (
    <Suspense fallback={<RedirectFallback />}>
      <ResearchToWhyInner />
    </Suspense>
  );
}

/** Old `/observability` URL → System (1:1 route rename; preserve query params). */
function ObservabilityToSystemInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const qs = searchParams.toString();
    router.replace(qs ? `/system?${qs}` : '/system');
  }, [router, searchParams]);

  return <RedirectFallback />;
}

export function ObservabilityToSystemRedirectPage() {
  return (
    <Suspense fallback={<RedirectFallback />}>
      <ObservabilityToSystemInner />
    </Suspense>
  );
}

/** Old `/portfolio/theses` hub → Portfolio "Theses" tab (preserve date). */
function ThesesHubToPortfolioInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const p = new URLSearchParams();
    p.set('tab', 'theses');
    const date = searchParams.get('date');
    if (date) p.set('date', date);
    router.replace(`/portfolio?${p.toString()}`);
  }, [router, searchParams]);

  return <RedirectFallback />;
}

export function ThesesHubToPortfolioRedirectPage() {
  return (
    <Suspense fallback={<RedirectFallback />}>
      <ThesesHubToPortfolioInner />
    </Suspense>
  );
}

/** Old `/architecture` URL → System (the "How Olympus works" explainer lives there now). */
function ArchitectureToSystemInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const qs = searchParams.toString();
    router.replace(qs ? `/system?${qs}` : '/system');
  }, [router, searchParams]);

  return <RedirectFallback />;
}

export function ArchitectureToSystemRedirectPage() {
  return (
    <Suspense fallback={<RedirectFallback />}>
      <ArchitectureToSystemInner />
    </Suspense>
  );
}
