/**
 * Payloads for the "desk" group: chat, settings, shell chrome.
 * Every type below is the envelope `data` shape of one GET route. Fields the
 * worker may not return yet are optional; null always renders "—".
 * Secrets: only `*_tail` fields ever arrive on a GET. A full key appears solely
 * in the response of POST /settings/keys, once.
 */

/** GET /chat/sessions -> { sessions } */
export type ChatSessionRow = { id: string; title?: string | null; updated_at?: string | null; message_count?: number | null; group?: string | null };
export type ChatSessions = { sessions: ChatSessionRow[]; active_id?: string | null };

/** GET /chat/sessions/current -> session header (also carries the id the composer posts to). */
export type ChatThread = {
  id: string;
  title?: string | null;
  message_count?: number | null;
  desk?: string | null;
  run_date?: string | null;
  artifacts?: { label: string; kind?: string | null; ref?: string | null }[] | null;
  can_send?: boolean | null;
};

/** GET /chat/sessions/current/messages -> { messages } */
export type ChatMessage = {
  id?: string | null;
  role?: 'user' | 'assistant' | 'tool' | string | null;
  text?: string | null;
  at?: string | null;
  /** Tool-call rows: name + status + (possibly long, JSON-ish) detail. */
  tool?: { name?: string | null; status?: string | null; detail?: string | null } | null;
};
export type ChatMessages = { messages: ChatMessage[] };

/** POST /chat/sessions/:id/messages body { text } -> { message_id?, reply?, status? } */
export type ChatSendResult = { message_id?: string | null; status?: string | null; reply?: string | null };

/** GET /settings/prefs (PUT same shape, partial allowed). */
export type Prefs = {
  display_name?: string | null;
  email?: string | null;
  density?: string | null;
  density_options?: string[] | null;
  daily_digest?: boolean | null;
  research_notices?: boolean | null;
};

/** GET /settings/desk */
export type SettingsDesk = {
  plan?: string | null;
  config?: string | null;
  config_note?: string | null;
  book_date?: string | null;
  posture?: string | null;
  /** Short mode tags such as "paper", "desk+". */
  tags?: string[] | null;
};

/** GET /settings/fx-feed */
export type FxFeedSettings = {
  grant?: string | null;
  posture?: string | null;
  feed?: { provider?: string | null; status?: string | null; last_tick?: string | null } | null;
  keys?: { label: string; tail?: string | null; status?: string | null }[] | null;
  generation?: { mode?: string | null; note?: string | null } | null;
};

/** GET /settings/brokers */
export type BrokerRow = { broker: string; env?: string | null; auth?: string | null; fingerprint_tail?: string | null; status?: string | null; last_used?: string | null };
export type Brokers = { brokers: BrokerRow[]; connectable?: string[] | null };
/** POST /settings/brokers/connect body { broker, env } -> { status?, detail?, auth_url? } */
export type BrokerConnectResult = { status?: string | null; detail?: string | null; auth_url?: string | null };

/** GET /settings/integrations */
export type IntegrationRow = { band: string; role?: string | null; key_tail?: string | null; status?: string | null };
export type Integrations = { integrations: IntegrationRow[]; note?: string | null };

/** GET /settings/keys */
export type KeyRow = { id: string; label?: string | null; tail?: string | null; scope?: string | null; status?: string | null; created_at?: string | null };
export type Keys = { keys: KeyRow[] };
/** POST /settings/keys body { label, scope } -> one-time { id, key, tail }. DELETE /settings/keys/:id -> 204. */
export type KeyMintResult = { id?: string | null; key?: string | null; tail?: string | null };

/** GET /desks */
export type DeskRow = { id: string; name: string; chip?: string | null; note?: string | null; spine?: string[] | null; active?: boolean | null };
export type Desks = { desks: DeskRow[]; hint?: string | null };

/** GET /desks/active/spine */
export type DeskSpine = { desk_id?: string | null; items: { no?: string | null; label: string; href?: string | null }[] };

/** GET /features */
export type FeatureFlag = { key: string; tag?: 'soon' | 'wip' | string | null; text?: string | null; action?: { label: string; href?: string | null } | null };
export type Features = { flags: FeatureFlag[] };

/** GET /pipeline/runs/latest */
export type LatestRun = { run_date?: string | null; status?: string | null; finished_at?: string | null; duration_s?: number | null };
