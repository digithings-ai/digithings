import { KpiGrid, Sparkline } from './atoms';
import { DataTable } from './DataTable';
import { Badge, BulletList, Button, KvList, MetaStrip, PageBand, Prose, SoonBar, StateBlock, Tabs } from './ui';
import { Window } from './Window';

const LONG = 'A deliberately long thesis sentence with an_unbroken_token_that_would_normally_blow_out_a_column_width_and_force_horizontal_scrolling_if_unclamped and then more words to wrap.';
const rows = [
  { id: 'T-007', name: 'Short', w: 12.5, v: 1.23, note: 'ok' },
  { id: 'T-008', name: LONG, w: 40, v: -4.5, note: LONG },
  { id: 'T-009', name: 'Null figures', w: null as number | null, v: null as number | null, note: '' },
];

/** Dev fixtures: every primitive with null / long / empty content. */
export function UiFixtures() {
  return (
    <div className="gal">
      <div className="gal-cell">
        <Window no="U1" label="DataTable · long / null">
          <DataTable
            rows={rows}
            rowKey={(r) => r.id}
            cols={[
              { key: 'i', label: 'Id', cell: (r) => r.id },
              { key: 'n', label: 'Name', wrap: true, cell: (r) => r.name },
              { key: 'w', label: 'Weight', num: true, bar: (r) => r.w, cell: (r) => (r.w == null ? '—' : `${r.w.toFixed(2)}%`) },
              { key: 'v', label: 'Value', num: true, tone: (r) => (r.v == null ? undefined : r.v >= 0 ? 'pos' : 'neg'), cell: (r) => (r.v == null ? '—' : r.v.toFixed(2)) },
            ]}
          />
        </Window>
      </div>
      <div className="gal-cell">
        <Window no="U2" label="Band · Tabs · Meta">
          <PageBand path="house / portfolio" title="Holdings" lede="Primitives render the same chrome on every page." meta={[{ label: 'Book date', value: '2026-09-30' }, { label: 'Broker', value: null }]} />
          <Tabs active="/portfolio/holdings" tabs={[{ href: '/portfolio/holdings', label: 'Holdings' }, { href: '/portfolio/ledger', label: 'Ledger' }, { href: '/portfolio/theses', label: 'Theses' }]} />
          <MetaStrip items={[{ label: 'Fills', value: 12 }, { label: 'Cash', value: '64.9%' }]} />
        </Window>
      </div>
      <div className="gal-cell">
        <Window no="U3" label="KPI · Badge · Kv">
          <KpiGrid items={[{ label: 'NAV', value: '99.909', note: 'finalized' }, { label: 'Day', value: '—' }, { label: 'Since', value: '+8.40%', tone: 'pos' }]} />
          <div className="pad"><Badge tone="ok">close</Badge> <Badge tone="wip">wip</Badge> <Badge tone="unavailable">unavailable</Badge> <Badge>plain</Badge></div>
          <KvList rows={[{ k: 'Ticker', v: 'XLF', mono: true }, { k: 'Notes', v: LONG }, { k: 'Broker', v: null }]} />
        </Window>
      </div>
      <div className="gal-cell">
        <Window no="U4" label="Prose · Bullets · Chart">
          <Prose lead="Lead sentence states the decision."><p>{LONG}</p></Prose>
          <BulletList items={['First risk', LONG]} />
          <div className="pad"><Sparkline values={[1, 3, 2, 5, 4, 6]} /></div>
        </Window>
      </div>
      <div className="gal-cell">
        <Window no="U5" label="States">
          <StateBlock kind="empty" title="No run yet." why="Empty until a run commits." next={[{ label: 'Open pipeline', href: '/pipeline' }]} />
          <StateBlock kind="loading" title="Waiting on the run." />
          <StateBlock kind="error" title="Withheld." why="The run failed; nothing is shown rather than a guess." next={[{ label: 'Retry' }]} />
        </Window>
      </div>
      <div className="gal-cell">
        <Window no="U6" label="SoonBar · Buttons">
          <SoonBar>Strategy deploy is not built yet.</SoonBar>
          <div className="pad"><Button primary>Deploy</Button> <Button disabled>Disabled</Button> <Button>Secondary</Button></div>
        </Window>
      </div>
    </div>
  );
}
