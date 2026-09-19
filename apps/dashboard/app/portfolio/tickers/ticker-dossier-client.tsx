'use client';

import { useSearchParams } from 'next/navigation';
import TickerDossierView from '@/components/portfolio/tickers/TickerDossierView';

/** `key` remounts the view when `?ticker=` changes (fresh fetch, no stale carry-over). */
export default function TickerDossierClient() {
  const searchParams = useSearchParams();
  const ticker = (searchParams.get('ticker') ?? '').trim().toUpperCase();
  return <TickerDossierView key={ticker} ticker={ticker} />;
}
