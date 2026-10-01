'use client';

import { useEffect, useState } from 'react';
import { dqGet, pct, px, signed, type Book, type BookRow } from '@/lib/dq-api';
import { DataTable, type Col } from './DataTable';
import { Window } from './Window';

const cols: Col<BookRow>[] = [
  { key: 't', label: 'Ticker', cell: (r) => r.ticker },
  { key: 'w', label: 'Weight', num: true, cell: (r) => pct(r.scaled_weight_pct) },
  { key: 'e', label: 'Entry', num: true, cell: (r) => px(r.entry_price) },
  { key: 'm', label: 'Mark', num: true, cell: (r) => px(r.current_price) },
  {
    key: 'u', label: 'Unrealised', num: true, cell: (r) => signed(r.unrealized_pct),
    tone: (r) => (r.unrealized_pct === null ? undefined : r.unrealized_pct >= 0 ? 'pos' : 'neg'),
  },
];

/** /book → GET /allocations (CONTRACT §6.2). */
export function BookTable() {
  const [book, setBook] = useState<Book | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    dqGet<Book>('/allocations').then((e) => setBook(e.data)).catch((e: unknown) => setErr(e instanceof Error ? e.message : 'failed'));
  }, []);

  return (
    <Window no="03" label="Book · allocation" right={book?.book_as_of ? `as of ${book.book_as_of}` : undefined}>
      {err ? <p className="note" role="alert">{err}</p>
        : !book ? <p className="note mute">loading…</p>
        : <DataTable rows={book.rows} cols={cols} rowKey={(r) => r.ticker} />}
    </Window>
  );
}
