'use client';

import { useEffect } from 'react';
import { initStarfield } from '@digithings/design/starfield.js';

export default function Starfield() {
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;
    return initStarfield({ canvasId: 'network-canvas', theme: 'auto' }).stop;
  }, []);

  return <canvas id="network-canvas" />;
}
