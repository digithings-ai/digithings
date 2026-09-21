'use client';

import { useEffect } from 'react';
import { Button } from '@digithings/ui/ui';
import { H1, LEDE } from '@/components/layout-constants';

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function Error({ error, reset }: ErrorProps) {
  useEffect(() => {
    console.error('[Dashboard Error]', error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-8 text-ink">
      <div className="max-w-md space-y-4 text-center">
        <h1 className={`${H1} text-down`}>Something went wrong</h1>
        <p className={LEDE}>
          {error?.message || 'An unexpected error occurred loading the dashboard.'}
        </p>
        <div className="flex justify-center gap-3 pt-2">
          <Button type="button" onClick={reset}>
            Try again
          </Button>
          <Button type="button" variant="outline" onClick={() => window.location.reload()}>
            Reload page
          </Button>
        </div>
      </div>
    </div>
  );
}
