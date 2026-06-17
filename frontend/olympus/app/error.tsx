'use client';

import { useEffect } from 'react';

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function Error({ error, reset }: ErrorProps) {
  useEffect(() => {
    console.error('[Dashboard Error]', error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary text-text-primary p-8">
      <div className="max-w-md text-center space-y-4">
        <h2 className="text-2xl font-bold text-fin-red">Something went wrong</h2>
        <p className="text-text-secondary text-sm">
          {error?.message || 'An unexpected error occurred loading the dashboard.'}
        </p>
        <div className="flex gap-3 justify-center pt-2">
          <button
            onClick={reset}
            className="px-4 py-2 border border-fin-blue/60 bg-fin-blue/15 hover:bg-fin-blue/25 text-text-primary rounded text-sm font-medium transition-colors"
          >
            Try again
          </button>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 border border-border-subtle hover:bg-text-primary/[0.06] text-text-secondary rounded text-sm font-medium transition-colors"
          >
            Reload page
          </button>
        </div>
      </div>
    </div>
  );
}
