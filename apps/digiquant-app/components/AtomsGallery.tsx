'use client';

import { useState } from 'react';
import { DataTable } from './DataTable';
import { Drawer } from './Drawer';
import { AreaChart, BarChart, type TPoint } from './charts-time';
import { Window } from './Window';

/** Dev page (/blocks/atoms): the v2 atoms on static SAMPLE props. Not real data; not reachable outside /blocks. */
const day = (i: number) => new Date(Date.UTC(2025, 9, 1) + i * 864e5 * 2).toISOString().slice(0, 10);
const SAMPLE_NAV: TPoint[] = Array.from({ length: 180 }, (_, i) => ({ t: day(i), v: 100 + i * 0.09 + Math.sin(i / 7) * 2.2 }));
const SAMPLE_DD: TPoint[] = (() => {
  let peak = -Infinity;
  return SAMPLE_NAV.map((p) => { peak = Math.max(peak, p.v as number); return { t: p.t, v: ((p.v as number) / peak - 1) * 100 }; });
})();
const SAMPLE_BARS = Array.from({ length: 14 }, (_, i) => ({ t: day(i * 10), v: i === 5 ? null : Math.sin(i * 1.3) * 3 }));
const SAMPLE_ROWS = Array.from({ length: 23 }, (_, i) => ({ sym: `SMP${String(i + 1).padStart(2, '0')}`, w: ((i * 37) % 17) + 1, d: i % 4 === 0 ? null : Math.cos(i) * 2 }));
type Row = (typeof SAMPLE_ROWS)[number];

const pct = (v: number) => `${v.toFixed(2)}%`;

export function AtomsGallery() {
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState<Row | null>(null);
  return (
    <div className="gal">
      <div className="gal-cell">
        <Window no="A1" label="DataTable v2" right="SAMPLE">
          <DataTable
            rows={SAMPLE_ROWS}
            rowKey={(r) => r.sym}
            filter
            stickyFirst
            pageSize={8}
            onRowClick={(r) => { setSel(r); setOpen(true); }}
            cols={[
              { key: 's', label: 'Symbol', sort: true, cell: (r) => r.sym },
              { key: 'w', label: 'Weight', num: true, sort: (r) => r.w, bar: (r) => r.w * 5, cell: (r) => pct(r.w) },
              { key: 'd', label: 'Day', num: true, sort: (r) => r.d, tone: (r) => (r.d == null ? undefined : r.d >= 0 ? 'pos' : 'neg'), cell: (r) => (r.d == null ? '—' : pct(r.d)) },
            ]}
          />
        </Window>
      </div>
      <div className="gal-cell">
        <Window no="A2" label="AreaChart · range tabs" right="SAMPLE">
          <AreaChart points={SAMPLE_NAV} ranges fmt={(v) => v.toFixed(1)} label="sample NAV" />
        </Window>
      </div>
      <div className="gal-cell">
        <Window no="A3" label="AreaChart · underwater" right="SAMPLE">
          <AreaChart points={SAMPLE_DD} underwater ranges={['3M', '6M', 'ALL']} fmt={pct} label="sample drawdown" />
        </Window>
      </div>
      <div className="gal-cell">
        <Window no="A4" label="BarChart · signed" right="SAMPLE">
          <BarChart bars={SAMPLE_BARS} fmt={pct} label="sample returns" />
        </Window>
      </div>
      <div className="gal-cell">
        <Window no="A5" label="Empty states" right="SAMPLE">
          <AreaChart points={[]} />
          <BarChart bars={[]} />
        </Window>
      </div>
      <Drawer open={open} onClose={() => setOpen(false)} no="D1" label={sel ? `Dossier ${sel.sym}` : 'Dossier'} right="SAMPLE">
        <p className="note mute">Sample dossier body. Esc closes; focus returns to the row.</p>
        <AreaChart points={SAMPLE_NAV} height={100} />
      </Drawer>
    </div>
  );
}
