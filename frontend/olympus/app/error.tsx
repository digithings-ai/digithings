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
    <div className="flex min-h-screen items-center justify-center bg-gray-950 text-white p-8">
      <div className="max-w-md text-center space-y-4">
        <h2 className="text-2xl font-bold text-red-400">Something went wrong</h2>
        <p className="text-gray-400 text-sm">
          {error?.message || 'An unexpected error occurred loading the dashboard.'}
        </p>
        <div className="flex gap-3 justify-center pt-2">
          <button
            onClick={reset}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm font-medium transition-colors"
          >
            Try again
          </button>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded text-sm font-medium transition-colors"
          >
            Reload page
          </button>
        </div>
      </div>
    </div>
  );
}
