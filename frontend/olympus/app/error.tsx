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
    <div className="flex min-h-screen items-center justify-center bg-bg text-ink p-8">
      <div className="max-w-md text-center space-y-4">
        <h2 className="text-2xl font-bold text-down">Something went wrong</h2>
        <p className="text-ink-soft text-sm">
          {error?.message || 'An unexpected error occurred loading the dashboard.'}
        </p>
        <div className="flex gap-3 justify-center pt-2">
          <button
            onClick={reset}
            className="px-4 py-2 border border-accent/60 bg-accent/15 hover:bg-accent/25 text-ink rounded text-sm font-medium transition-colors"
          >
            Try again
          </button>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 border border-hair hover:bg-ink/[0.06] text-ink-soft rounded text-sm font-medium transition-colors"
          >
            Reload page
          </button>
        </div>
      </div>
    </div>
  );
}
