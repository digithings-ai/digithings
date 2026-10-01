'use client';

import { BLOCKS } from './blocks';

/** Dev gallery: every registered block in a plain grid, for review before pages are composed. */
export function Gallery() {
  return (
    <div className="gal">
      {BLOCKS.map(({ id, Component }) => (
        <div key={id} className="gal-cell"><Component /></div>
      ))}
    </div>
  );
}
