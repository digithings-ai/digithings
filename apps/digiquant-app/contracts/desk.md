# Contract fragment: desk group (chat, settings, shell)

All routes return the standard envelope `{ data, as_of, provenance }`. Types: `lib/api-desk.ts`. Every route below is **new**. Optional fields may be omitted or null; the UI shows "—" and never defaults. Secrets: GET responses carry only `*_tail` (last 4 chars). Source tables are a suggestion (dashboard-api currently exposes none of these; chat/settings need new tables or a digichat/digikey proxy).

## Chat
| route | data | source |
|---|---|---|
| `GET /chat/sessions` | `{ sessions: {id, title?, updated_at?, message_count?, group?}[], active_id? }` — `group` is a recency label (Today, Yesterday, ...), pre-sorted newest first | digichat sessions (per user) |
| `GET /chat/sessions/current` | `{ id, title?, message_count?, desk?, run_date?, artifacts?: {label, kind?, ref?}[], can_send? }`. `current` aliases the user's most recent session; `/chat/sessions/:id` should behave identically. `id` is what the composer posts to | digichat |
| `GET /chat/sessions/current/messages` | `{ messages: {id?, role?, text?, at?, tool?: {name?, status?, detail?}}[] }`. `detail` may be long JSON text; null text with a `tool` is a tool-call row | digichat messages |
| `POST /chat/sessions/:id/messages` | body `{ text: string }` -> `{ message_id?, status?, reply? }`; 422 on empty text. UI shows server status/error text only | digichat |

## Settings
| route | data | source |
|---|---|---|
| `GET /settings/prefs` | `{ display_name?, email?, density?, density_options?: string[], daily_digest?: bool\|null, research_notices?: bool\|null }`; null boolean = "not set" (rendered off with a hint) | digikey user prefs |
| `PUT /settings/prefs` | body `{ display_name, email, density, daily_digest, research_notices }` (empty strings sent as null) -> any 2xx; 422 on invalid | digikey |
| `GET /settings/desk` | `{ plan?, config?, config_note?, book_date?, posture?, tags?: string[] }` (also drives footer-status) | desk config + `nav_series` tip for book_date |
| `GET /settings/fx-feed` | `{ grant?, posture?, feed?: {provider?, status?, last_tick?}, keys?: {label, tail?, status?}[], generation?: {mode?, note?} }` | FX feed config |
| `GET /settings/brokers` | `{ brokers: {broker, env?, auth?, fingerprint_tail?, status?, last_used?}[], connectable?: string[] }` | broker connections |
| `POST /settings/brokers/connect` | body `{ broker, env: "paper" }` -> `{ status?, detail?, auth_url? }`; 422 if broker missing | broker connector |
| `GET /settings/integrations` | `{ integrations: {band, role?, key_tail?, status?}[], note? }` | integrations registry |
| `GET /settings/keys` | `{ keys: {id, label?, tail?, scope?, status?, created_at?}[] }` — never a full key | digikey |
| `POST /settings/keys` | body `{ label, scope? }` -> `{ id, key, tail }`; `key` is the only time a full secret leaves the API. 422 if label missing | digikey |
| `DELETE /settings/keys/:id` | 204 on success, 404 if unknown | digikey |

## Shell
| route | data | source |
|---|---|---|
| `GET /desks` | `{ desks: {id, name, chip?, note?, spine?: string[], active?}[], hint? }` | desk configs |
| `GET /desks/active/spine` | `{ desk_id?, items: {no?, label, href?}[] }` (`/desks/:id/spine` same shape; `active` = the caller's current desk) | desk configs |
| `GET /features` | `{ flags: {key, tag?: "soon"\|"wip", text?, action?: {label, href?}}[] }` | feature flag config |
| `GET /pipeline/runs/latest` | `{ run_date?, status?, finished_at?, duration_s? }` | `run_health` latest row |

Notes: footer-status reuses `GET /settings/desk`; ch-composer reuses `GET /chat/sessions/current`. Null semantics: absent/null never means zero or "ok"; unknown status renders as a plain badge.
