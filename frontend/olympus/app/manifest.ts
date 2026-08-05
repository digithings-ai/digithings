import type { MetadataRoute } from 'next';

export const dynamic = 'force-static';

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'Olympus — DigiQuant',
    short_name: 'Olympus',
    description: 'AI-orchestrated investment intelligence from DigiQuant.',
    start_url: '/olympus/',
    scope: '/olympus/',
    display: 'standalone',
    background_color: '#0A0E0C',
    theme_color: '#0A0E0C',
    icons: [
      {
        src: '/olympus/icons/olympus-app-192.png',
        sizes: '192x192',
        type: 'image/png',
      },
      {
        src: '/olympus/icons/olympus-app-512.png',
        sizes: '512x512',
        type: 'image/png',
      },
      {
        src: '/olympus/icons/olympus-app-maskable-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}