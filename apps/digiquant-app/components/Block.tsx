'use client';

import type { ReactNode } from 'react';
import type { Envelope } from '@/lib/dq-api';
import { useRoute } from '@/lib/use-route';
import { StateBlock } from './ui';
import { Window } from './Window';

/**
 * Block = Window + one API route. Handles loading/error uniformly so each
 * block only describes how to draw its payload.
 */
export function Block<T>({ no, label, route, asOf, children }: {
  no: string;
  label: string;
  route: string;
  asOf?: (d: T) => string | null | undefined;
  children: (data: T, env: Envelope<T>) => ReactNode;
}) {
  const { env, err } = useRoute<T>(route);
  const stamp = env ? (asOf?.(env.data) ?? env.as_of) : null;
  return (
    <Window no={no} label={label} right={stamp ? `as of ${stamp}` : route}>
      {err ? <StateBlock kind="error" title="Withheld." why={`${route}: ${err}`} />
        : !env ? <p className="note mute">loading…</p>
        : children(env.data, env)}
    </Window>
  );
}
