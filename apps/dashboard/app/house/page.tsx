'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/**
 * `house` is a desk name. Corpus, Book, and Profile are not a route.
 * Bookmarks land on Brief. Static-export safe (client replace, same as /system).
 */
export default function HousePage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/');
  }, [router]);
  return (
    <p className="px-4 py-8 font-mono text-xs text-ink-mute" role="status">
      Redirecting to Brief…
    </p>
  );
}
