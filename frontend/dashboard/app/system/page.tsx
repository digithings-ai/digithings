'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** Legacy System surface — run health moved to Pipeline; bookmarks land there. */
export default function SystemRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/pipeline');
  }, [router]);
  return (
    <p className="px-4 py-8 font-mono text-xs text-ink-mute" role="status">
      Redirecting to Pipeline…
    </p>
  );
}
