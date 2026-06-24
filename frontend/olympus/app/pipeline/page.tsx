'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import AtlasLoader from '@/components/AtlasLoader';

/**
 * Placeholder for the Pipeline hub (Surface 1, separate locked build). Until
 * that build lands, /pipeline redirects to the legacy /why surface so the
 * renamed nav target never 404s. Replaced wholesale by the Pipeline canvas.
 */
export default function PipelinePage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/why');
  }, [router]);
  return <AtlasLoader />;
}
