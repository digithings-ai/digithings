'use client';

import { useEffect } from 'react';
import { Button } from '@digithings/web/ui';

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function Error({ error, reset }: ErrorProps) {
  useEffect(() => {
    console.error('[Dashboard Error]', error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg text-ink p-8">
      <div className="max-w-md text-center space-y-4">
        <h2 className="text-2xl font-bold text-danger">Something went wrong</h2>
        <p className="text-ink-soft text-sm">
          {error?.message || 'An unexpected error occurred loading the dashboard.'}
        </p>
        <div className="flex gap-3 justify-center pt-2">
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
