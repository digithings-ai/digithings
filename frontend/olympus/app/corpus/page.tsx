import { Suspense } from 'react';
import PageSkeleton from '@/components/page-skeleton';
import CorpusShellInner from '@/components/corpus/CorpusShellInner';

export default function CorpusPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <CorpusShellInner />
    </Suspense>
  );
}
