import type { MetadataRoute } from 'next';

export const dynamic = 'force-static';

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'digiquant',
    short_name: 'digiquant',
    description: 'AI-orchestrated investment intelligence from digiquant.',
    start_url: '/dashboard/',
    scope: '/dashboard/',
    display: 'standalone',
    background_color: '#0A0E0C', // canon-allow: manifests cannot reference CSS tokens
    theme_color: '#0A0E0C', // canon-allow: manifests cannot reference CSS tokens
    icons: [
      {
        src: '/dashboard/icons/dashboard-app-192.png',
        sizes: '192x192',
        type: 'image/png',
      },
      {
        src: '/dashboard/icons/dashboard-app-512.png',
        sizes: '512x512',
        type: 'image/png',
      },
      {
        src: '/dashboard/icons/dashboard-app-maskable-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}