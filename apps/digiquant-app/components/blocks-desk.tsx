'use client';

import Link from 'next/link';
import { useState, type ComponentType, type ReactNode } from 'react';
import { dqSend } from '@/lib/dq-api';
import type {
  BrokerConnectResult, Brokers, ChatMessages, ChatSendResult, ChatSessions, ChatThread, Desks, DeskSpine, Features, FxFeedSettings,
  Integrations, KeyMintResult, Keys, LatestRun, Prefs, SettingsDesk,
} from '@/lib/api-desk';
import { Block } from './Block';
import { DataTable } from './DataTable';
import { Badge, Button, KvList, MetaStrip, SoonBar, StateBlock, type BadgeTone } from './ui';
import { Field, SecretField, Select, Toggle } from './ui-form';

/* Styles used from styles/desk.css (prefix dk-): dk-grp dk-sess dk-msg dk-who dk-body dk-tool dk-res dk-once dk-spine dk-desk. */

const dash = (v: ReactNode | null | undefined) => (v == null || v === '' ? '—' : v);
const arr = <T,>(v: T[] | null | undefined): T[] => (Array.isArray(v) ? v : []);
const tail = (t: string | null | undefined) => (t ? `…${t}` : '—');
const withheld = (what: string) => <StateBlock kind="empty" title="Withheld." why={`${what} is not in the response yet; nothing is estimated.`} />;
const statusTone = (s: string | null | undefined): BadgeTone => {
  const v = (s ?? '').toLowerCase();
  if (['ok', 'active', 'connected', 'succeeded', 'success', 'live'].includes(v)) return 'ok';
  if (['wip', 'pending', 'running', 'watch', 'stub'].includes(v)) return 'wip';
  if (['failed', 'error', 'revoked', 'disconnected', 'gap'].includes(v)) return 'gap';
  return 'plain';
};
const stateBadge = (s: string | null | undefined) => (s ? <Badge tone={statusTone(s)}>{s}</Badge> : '—');

/** One write at a time per control; result text always rendered, success only after a 2xx. */
type Res = { kind: 'idle' | 'busy' | 'ok' | 'err'; text: string };
const IDLE: Res = { kind: 'idle', text: '' };
function ResultLine({ res }: { res: Res }) {
  if (res.kind === 'idle') return null;
  return <p className={`note dk-res ${res.kind}`} role={res.kind === 'err' ? 'alert' : 'status'}>{res.kind === 'busy' ? 'working…' : res.text}</p>;
}
const errText = (e: unknown) => (e instanceof Error ? e.message : 'request failed');

/* ================= CHAT ================= */

/** GET /chat/sessions — session list grouped by recency. */
export function ChatSessionsBlock() {
  return (
    <Block<ChatSessions> no="CH1" label="Chat · sessions" route="/chat/sessions">
      {(d) => {
        const rows = arr(d.sessions);
        if (!rows.length) return <p className="note mute">no sessions</p>;
        const out: ReactNode[] = [];
        let last: string | null | undefined = undefined;
        rows.forEach((s, i) => {
          const g = s.group ?? null;
          if (g !== last && g) out.push(<div key={`g${i}`} className="dk-grp">{g}</div>);
          last = g;
          out.push(
            <div key={`${s.id}:${i}`} className="dk-sess" aria-current={d.active_id != null && d.active_id === s.id ? 'true' : undefined}>
              <span className="dk-sess-t">{dash(s.title)}</span>
              <span className="meta">{s.message_count != null && Number.isFinite(s.message_count) ? `${s.message_count} msg` : '—'} · {dash(s.updated_at)}</span>
            </div>,
          );
        });
        return <div>{out}</div>;
      }}
    </Block>
  );
}

/** GET /chat/sessions/current — thread header and artifacts in view. */
export function ChatThreadBlock() {
  return (
    <Block<ChatThread> no="CH2" label="Chat · thread" route="/chat/sessions/current" asOf={(d) => d.run_date}>
      {(d) => (
        <>
          <p className="pad"><b>{dash(d.title)}</b></p>
          <MetaStrip items={[
            { label: 'Session', value: d.id },
            { label: 'Messages', value: d.message_count != null && Number.isFinite(d.message_count) ? String(d.message_count) : null },
            { label: 'Desk', value: d.desk },
          ]} />
          {Array.isArray(d.artifacts) ? (
            <DataTable
              rows={d.artifacts}
              rowKey={(a, i) => `${a.label}:${i}`}
              empty="no artifacts in view"
              cols={[
                { key: 'l', label: 'Artifact', wrap: true, cell: (a) => dash(a.label) },
                { key: 'k', label: 'Kind', cell: (a) => dash(a.kind) },
                { key: 'r', label: 'Ref', wrap: true, cell: (a) => dash(a.ref) },
              ]}
            />
          ) : withheld('artifacts')}
        </>
      )}
    </Block>
  );
}

/** GET /chat/sessions/current/messages — transcript with tool-call rows. */
export function ChatTranscriptBlock() {
  return (
    <Block<ChatMessages> no="CH3" label="Chat · transcript" route="/chat/sessions/current/messages">
      {(d) => {
        const ms = arr(d.messages);
        if (!ms.length) return <p className="note mute">no messages</p>;
        return (
          <div>
            {ms.map((m, i) => (
              <article key={`${m.id ?? 'm'}:${i}`} className="dk-msg" data-role={m.role ?? 'unknown'}>
                <div className="dk-who">{dash(m.role === 'assistant' ? 'digichat' : m.role)}{m.at ? <span className="mute"> · {m.at}</span> : null}</div>
                {m.tool ? (
                  <div className="dk-tool">
                    <span className="mono">tool {dash(m.tool.name)}</span> {m.tool.status ? <Badge tone={statusTone(m.tool.status)}>{m.tool.status}</Badge> : null}
                    {m.tool.detail ? <pre className="dk-body mono">{m.tool.detail}</pre> : null}
                  </div>
                ) : null}
                {m.text ? <p className="dk-body">{m.text}</p> : !m.tool ? <p className="dk-body mute">—</p> : null}
              </article>
            ))}
          </div>
        );
      }}
    </Block>
  );
}

function Composer({ d }: { d: ChatThread }) {
  const [text, setText] = useState('');
  const [res, setRes] = useState<Res>(IDLE);
  const blocked = d.can_send === false || !d.id;
  const send = async () => {
    const t = text.trim();
    if (!t || blocked || res.kind === 'busy') return;
    setRes({ kind: 'busy', text: '' });
    try {
      const r = await dqSend<ChatSendResult>('POST', `/chat/sessions/${encodeURIComponent(d.id)}/messages`, { text: t });
      setText('');
      setRes({ kind: 'ok', text: [`server accepted${r?.status ? ` (${r.status})` : ''}`, r?.reply ? `reply: ${r.reply}` : null].filter(Boolean).join(' · ') });
    } catch (e) {
      setRes({ kind: 'err', text: errText(e) });
    }
  };
  return (
    <>
      <Field
        label="Message"
        value={text}
        placeholder="Ask about this run"
        disabled={blocked}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') void send(); }}
        hint={blocked ? 'This session cannot accept messages.' : undefined}
      />
      <p className="pad"><Button primary disabled={blocked || !text.trim() || res.kind === 'busy'} onClick={() => void send()}>Send</Button></p>
      <ResultLine res={res} />
    </>
  );
}

/** GET /chat/sessions/current (session id, can_send) + POST /chat/sessions/:id/messages. */
export function ChatComposerBlock() {
  return (
    <Block<ChatThread> no="CH4" label="Chat · composer" route="/chat/sessions/current">
      {(d) => <Composer d={d} />}
    </Block>
  );
}

/* ================= SETTINGS ================= */

function PrefsForm({ d }: { d: Prefs }) {
  const [name, setName] = useState(d.display_name ?? '');
  const [email, setEmail] = useState(d.email ?? '');
  const [density, setDensity] = useState(d.density ?? '');
  const [digest, setDigest] = useState(d.daily_digest === true);
  const [notices, setNotices] = useState(d.research_notices === true);
  const [res, setRes] = useState<Res>(IDLE);
  const opts = arr(d.density_options).map((o) => ({ value: o, label: o }));
  if (d.density && !opts.some((o) => o.value === d.density)) opts.unshift({ value: d.density, label: d.density });
  const options = [{ value: '', label: '—' }, ...opts];
  const save = async () => {
    setRes({ kind: 'busy', text: '' });
    try {
      await dqSend('PUT', '/settings/prefs', {
        display_name: name.trim() || null, email: email.trim() || null, density: density || null, daily_digest: digest, research_notices: notices,
      });
      setRes({ kind: 'ok', text: 'saved (server returned success)' });
    } catch (e) {
      setRes({ kind: 'err', text: errText(e) });
    }
  };
  return (
    <>
      <Field label="Display name" value={name} onChange={(e) => setName(e.target.value)} placeholder="—" />
      <Field label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="—" hint="Empty until saved." />
      <Select label="Density" options={options} value={density} onChange={setDensity} />
      <Toggle label="Daily digest" on={digest} onChange={setDigest} hint={d.daily_digest == null ? 'not set' : undefined} />
      <Toggle label="Research notices" on={notices} onChange={setNotices} hint={d.research_notices == null ? 'not set' : undefined} />
      <p className="pad"><Button primary disabled={res.kind === 'busy'} onClick={() => void save()}>Save prefs</Button></p>
      <ResultLine res={res} />
    </>
  );
}

/** GET /settings/prefs + PUT /settings/prefs. */
export function SettingsPrefsBlock() {
  return <Block<Prefs> no="SE1" label="Settings · prefs" route="/settings/prefs">{(d) => <PrefsForm d={d} />}</Block>;
}

/** GET /settings/desk — plan and desk config. */
export function SettingsDeskBlock() {
  return (
    <Block<SettingsDesk> no="SE2" label="Settings · desk" route="/settings/desk" asOf={(d) => d.book_date}>
      {(d) => (
        <>
          <KvList rows={[
            { k: 'Plan', v: d.plan },
            { k: 'Config', v: d.config ? `${d.config}${d.config_note ? ` · ${d.config_note}` : ''}` : null },
            { k: 'Book date', v: d.book_date, mono: true },
            { k: 'Posture', v: d.posture },
          ]} />
          {arr(d.tags).length ? <p className="pad">{arr(d.tags).map((t, i) => <span key={`${t}:${i}`}><Badge>{t}</Badge> </span>)}</p> : null}
        </>
      )}
    </Block>
  );
}

/** GET /settings/fx-feed — FX feed, stub keys (tail only). */
export function SettingsFxFeedBlock() {
  return (
    <Block<FxFeedSettings> no="SE3" label="Settings · FX feed" route="/settings/fx-feed" asOf={(d) => d.feed?.last_tick}>
      {(d) => (
        <>
          <MetaStrip items={[{ label: 'Grant', value: d.grant }, { label: 'Posture', value: d.posture }, { label: 'Feed', value: d.feed?.provider }, { label: 'Status', value: d.feed?.status }]} />
          {Array.isArray(d.keys) ? (d.keys.length ? d.keys.map((k, i) => <SecretField key={`${k.label}:${i}`} label={k.label} tail={k.tail} hint={k.status ?? undefined} />) : <p className="note mute">no keys</p>) : withheld('feed keys')}
          {d.generation ? <p className="note">Generation: {dash(d.generation.mode)}{d.generation.note ? ` — ${d.generation.note}` : ''}</p> : null}
        </>
      )}
    </Block>
  );
}

function BrokerConnect({ options }: { options: string[] }) {
  const [broker, setBroker] = useState('');
  const [res, setRes] = useState<Res>(IDLE);
  const go = async () => {
    const b = broker.trim();
    if (!b) return;
    setRes({ kind: 'busy', text: '' });
    try {
      const r = await dqSend<BrokerConnectResult>('POST', '/settings/brokers/connect', { broker: b, env: 'paper' });
      setRes({ kind: 'ok', text: [r?.status ?? 'server accepted', r?.detail, r?.auth_url ? `continue at ${r.auth_url}` : null].filter(Boolean).join(' · ') });
    } catch (e) {
      setRes({ kind: 'err', text: errText(e) });
    }
  };
  return (
    <>
      <Field label="Broker" value={broker} onChange={(e) => setBroker(e.target.value)} list="dk-broker-opts" placeholder="paper broker id" hint="Paper environment only." onKeyDown={(e) => { if (e.key === 'Enter') void go(); }} />
      {options.length ? <datalist id="dk-broker-opts">{options.map((o) => <option key={o} value={o} />)}</datalist> : null}
      <p className="pad"><Button primary disabled={!broker.trim() || res.kind === 'busy'} onClick={() => void go()}>Connect paper broker</Button></p>
      <ResultLine res={res} />
    </>
  );
}

/** GET /settings/brokers + POST /settings/brokers/connect. */
export function SettingsBrokersBlock() {
  return (
    <Block<Brokers> no="SE4" label="Settings · brokers" route="/settings/brokers">
      {(d) => (
        <>
          <DataTable
            rows={arr(d.brokers)}
            rowKey={(b, i) => `${b.broker}:${i}`}
            empty="no brokers connected"
            cols={[
              { key: 'b', label: 'Broker', cell: (b) => dash(b.broker) },
              { key: 'e', label: 'Env', cell: (b) => dash(b.env) },
              { key: 'a', label: 'Auth', cell: (b) => dash(b.auth) },
              { key: 'f', label: 'Fingerprint', cell: (b) => tail(b.fingerprint_tail) },
              { key: 's', label: 'Status', cell: (b) => stateBadge(b.status) },
              { key: 'l', label: 'Last used', cell: (b) => dash(b.last_used) },
            ]}
          />
          <BrokerConnect options={arr(d.connectable)} />
        </>
      )}
    </Block>
  );
}

/** GET /settings/integrations — named bands (key tail only). */
export function SettingsIntegrationsBlock() {
  return (
    <Block<Integrations> no="SE5" label="Settings · integrations" route="/settings/integrations">
      {(d) => (
        <>
          <DataTable
            rows={arr(d.integrations)}
            rowKey={(r, i) => `${r.band}:${i}`}
            empty="no integrations"
            cols={[
              { key: 'b', label: 'Band', cell: (r) => dash(r.band) },
              { key: 'r', label: 'Role', wrap: true, cell: (r) => dash(r.role) },
              { key: 'k', label: 'Key', cell: (r) => tail(r.key_tail) },
              { key: 's', label: 'Status', cell: (r) => stateBadge(r.status) },
            ]}
          />
          {d.note ? <p className="note">{d.note}</p> : null}
        </>
      )}
    </Block>
  );
}

function KeysPanel({ d }: { d: Keys }) {
  const [label, setLabel] = useState('');
  const [scope, setScope] = useState('');
  const [mint, setMint] = useState<Res>(IDLE);
  const [once, setOnce] = useState<KeyMintResult | null>(null);
  const [arm, setArm] = useState<string | null>(null);
  const [revoked, setRevoked] = useState<Record<string, true>>({});
  const [rev, setRev] = useState<Res>(IDLE);

  const doMint = async () => {
    if (!label.trim()) return;
    setMint({ kind: 'busy', text: '' });
    setOnce(null);
    try {
      const r = await dqSend<KeyMintResult>('POST', '/settings/keys', { label: label.trim(), scope: scope.trim() || null });
      if (r?.key) setOnce(r);
      setMint({ kind: 'ok', text: r?.key ? 'key minted — copy it now' : 'server accepted but returned no key' });
      setLabel('');
    } catch (e) {
      setMint({ kind: 'err', text: errText(e) });
    }
  };
  const doRevoke = async (id: string) => {
    setArm(null);
    setRev({ kind: 'busy', text: '' });
    try {
      await dqSend('DELETE', `/settings/keys/${encodeURIComponent(id)}`);
      setRevoked((p) => ({ ...p, [id]: true }));
      setRev({ kind: 'ok', text: `revoked ${id}` });
    } catch (e) {
      setRev({ kind: 'err', text: errText(e) });
    }
  };
  return (
    <>
      <DataTable
        rows={arr(d.keys)}
        rowKey={(k, i) => `${k.id}:${i}`}
        empty="no keys"
        cols={[
          { key: 'l', label: 'Label', wrap: true, cell: (k) => dash(k.label) },
          { key: 'k', label: 'Key', cell: (k) => (k.tail ? `••••${k.tail}` : '—') },
          { key: 's', label: 'Scope', wrap: true, cell: (k) => dash(k.scope) },
          { key: 'st', label: 'Status', cell: (k) => stateBadge(revoked[k.id] ? 'revoked' : k.status) },
          {
            key: 'x', label: '', cell: (k) => (revoked[k.id] || k.status === 'revoked' ? '' : arm === k.id
              ? <><Button onClick={() => void doRevoke(k.id)}>confirm revoke</Button> <Button onClick={() => setArm(null)}>cancel</Button></>
              : <Button onClick={() => setArm(k.id)}>revoke</Button>),
          },
        ]}
      />
      <ResultLine res={rev} />
      <Field label="New key label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. desk read" />
      <Field label="Scope" value={scope} onChange={(e) => setScope(e.target.value)} placeholder="optional" />
      <p className="pad"><Button primary disabled={!label.trim() || mint.kind === 'busy'} onClick={() => void doMint()}>Mint key</Button></p>
      <ResultLine res={mint} />
      {once?.key ? (
        <div className="dk-once" role="status">
          <p className="meta">Shown once. It is not stored here and cannot be read again.</p>
          <code className="mono dk-body">{once.key}</code>
          <p><Button onClick={() => setOnce(null)}>dismiss</Button></p>
        </div>
      ) : null}
    </>
  );
}

/** GET /settings/keys (tail only) + POST /settings/keys (mint) + DELETE /settings/keys/:id (revoke). */
export function SettingsKeysBlock() {
  return <Block<Keys> no="SE6" label="Settings · API keys" route="/settings/keys">{(d) => <KeysPanel d={d} />}</Block>;
}

/* ================= SHELL ================= */

/** GET /desks — desk picker list. */
export function DesksBlock() {
  return (
    <Block<Desks> no="SH1" label="Desks" route="/desks">
      {(d) => (
        <>
          {arr(d.desks).length ? arr(d.desks).map((x, i) => (
            <div key={`${x.id}:${i}`} className="dk-desk" aria-current={x.active ? 'true' : undefined}>
              <div><b>{dash(x.name)}</b> {x.chip ? <Badge>{x.chip}</Badge> : null}</div>
              {x.note ? <div className="meta">{x.note}</div> : null}
              {arr(x.spine).length ? <div className="dk-spine">{arr(x.spine).join(' · ')}</div> : null}
            </div>
          )) : <p className="note mute">no desks</p>}
          {d.hint ? <p className="note">{d.hint}</p> : null}
        </>
      )}
    </Block>
  );
}

/** GET /desks/active/spine — the active desk's navigation items. */
export function DeskSpineBlock() {
  return (
    <Block<DeskSpine> no="SH2" label="Desk · spine" route="/desks/active/spine">
      {(d) => (arr(d.items).length ? (
        <DataTable
          rows={arr(d.items)}
          rowKey={(s, i) => `${s.label}:${i}`}
          cols={[
            { key: 'n', label: 'No', cell: (s) => dash(s.no) },
            { key: 'l', label: 'Page', wrap: true, cell: (s) => (s.href ? <Link href={s.href}>{s.label}</Link> : dash(s.label)) },
          ]}
        />
      ) : <p className="note mute">no spine items</p>)}
    </Block>
  );
}

/** GET /features — soon/wip flags as soon-bars. */
export function FeaturesBlock() {
  return (
    <Block<Features> no="SH3" label="Features" route="/features">
      {(d) => (arr(d.flags).length ? (
        <>
          {arr(d.flags).map((f, i) => (
            <SoonBar key={`${f.key}:${i}`} tag={f.tag === 'wip' ? 'wip' : 'soon'}>
              {dash(f.text ?? f.key)}
              {f.action?.label ? <> {f.action.href ? <Link href={f.action.href}>{f.action.label} →</Link> : <span className="mute">{f.action.label}</span>}</> : null}
            </SoonBar>
          ))}
        </>
      ) : <p className="note mute">no flags</p>)}
    </Block>
  );
}

/** GET /pipeline/runs/latest — tiny status chip. */
export function PipelineStatusChipBlock() {
  return (
    <Block<LatestRun> no="SH4" label="Pipeline · latest" route="/pipeline/runs/latest" asOf={(d) => d.run_date}>
      {(d) => (
        <p className="pad">
          {stateBadge(d.status)} <span className="mono">{dash(d.run_date)}</span>
          <span className="mute"> · {d.duration_s != null && Number.isFinite(d.duration_s) ? `${Math.round(d.duration_s)}s` : '—'}</span>
        </p>
      )}
    </Block>
  );
}

/** GET /settings/desk — footer tags and desk name. */
export function FooterStatusBlock() {
  return (
    <Block<SettingsDesk> no="SH5" label="Footer · status" route="/settings/desk" asOf={(d) => d.book_date}>
      {(d) => (
        <p className="pad meta">
          {arr(d.tags).map((t, i) => <span key={`${t}:${i}`}><Badge>{t}</Badge></span>)}
          <span>digiquant · {dash(d.config)}</span>
          {d.plan ? <span>{d.plan}</span> : null}
        </p>
      )}
    </Block>
  );
}

export type DeskBlockDef = { id: string; title: string; route: string; Component: ComponentType };
export const DESK_BLOCKS: DeskBlockDef[] = [
  { id: 'ch-sessions', title: 'Chat · sessions', route: '/chat/sessions', Component: ChatSessionsBlock },
  { id: 'ch-thread', title: 'Chat · thread', route: '/chat/sessions/current', Component: ChatThreadBlock },
  { id: 'ch-transcript', title: 'Chat · transcript', route: '/chat/sessions/current/messages', Component: ChatTranscriptBlock },
  { id: 'ch-composer', title: 'Chat · composer', route: '/chat/sessions/current', Component: ChatComposerBlock },
  { id: 'se-prefs', title: 'Settings · prefs', route: '/settings/prefs', Component: SettingsPrefsBlock },
  { id: 'se-desk', title: 'Settings · desk', route: '/settings/desk', Component: SettingsDeskBlock },
  { id: 'se-fx-feed', title: 'Settings · FX feed', route: '/settings/fx-feed', Component: SettingsFxFeedBlock },
  { id: 'se-brokers', title: 'Settings · brokers', route: '/settings/brokers', Component: SettingsBrokersBlock },
  { id: 'se-integrations', title: 'Settings · integrations', route: '/settings/integrations', Component: SettingsIntegrationsBlock },
  { id: 'se-keys', title: 'Settings · API keys', route: '/settings/keys', Component: SettingsKeysBlock },
  { id: 'sh-desks', title: 'Desks', route: '/desks', Component: DesksBlock },
  { id: 'sh-spine', title: 'Desk · spine', route: '/desks/active/spine', Component: DeskSpineBlock },
  { id: 'sh-features', title: 'Features', route: '/features', Component: FeaturesBlock },
  { id: 'sh-pipeline-chip', title: 'Pipeline · latest', route: '/pipeline/runs/latest', Component: PipelineStatusChipBlock },
  { id: 'sh-footer', title: 'Footer · status', route: '/settings/desk', Component: FooterStatusBlock },
];
