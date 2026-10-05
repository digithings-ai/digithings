'use client';

import { Component, type ReactNode } from 'react';
import { blockAgeFooter, type BlockAge } from '@/lib/block-age';
import type { Envelope } from '@/lib/dq-api';
import { useRoute } from '@/lib/use-route';
import { StateBlock } from './ui';
import { Window } from './Window';

/** One block throwing on odd data must not take the page down. */
class Guard extends Component<{ route: string; children: ReactNode }, { err: string | null }> {
  state = { err: null as string | null };
  static getDerivedStateFromError(e: unknown) { return { err: e instanceof Error ? e.message : 'render failed' }; }
  render() {
    return this.state.err
      ? <StateBlock kind="error" title="Withheld." why={`${this.props.route}: unexpected response shape (${this.state.err})`} />
      : this.props.children;
  }
}

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
  // Age is claimed only once there is a session-bearing date to age; otherwise the
  // bar falls back to the route, exactly as it did before this was added.
  const age = blockAgeFooter({ runDate: stamp, route });
  return (
    <Window no={no} label={label} right={
      <>
        {age.lead}
        {/* The state word is the severity claim, so it also carries ink. */}
        {age.state ? <span className={`win-age ${age.state}`}> {age.state}</span> : null}
      </>
    }>
      {err ? <StateBlock kind="error" title="Withheld." why={err.startsWith(route) ? err : `${route}: ${err}`} />
        : !env ? <p className="note mute">loading…</p>
        : <Guard key={env.as_of ?? route} route={route}>{children(env.data, env)}</Guard>}
    </Window>
  );
}
