# digichat skin gallery — the one place for UI work

**Start here for any digichat UI work.** The gallery mounts every skin we ship
against a single backend, so you can iterate on a skin, compare skins, or add a
new one without standing up a deployment per variant.

Surface: `http://127.0.0.1:3000/baseline` — pick a skin from the top bar, toggle
light/dark, and chat. The skin is a parameter; everything else is shared.

```bash
make digichat-dev            # from the repo root
# → http://127.0.0.1:3000/baseline
```

`apps/digichat/.env.local` is required (see [`STOCK-SMOKE.md`](STOCK-SMOKE.md) for
the dev env). Append `&theme=dark` to start dark; the default is light.

This is a **development surface only.** The page calls `notFound()` in a
production build, and its BFF route 404s outside the dev loopback (below).

---

## The model: one deployment, any skin

A digichat deployment already takes a skin — it is `chrome.skin` in the deploy
config, resolved to a `ThreadSkin` id. The gallery is the surface that exercises
**every** value of that parameter against one backend:

| Layer | What it is | Where it lives |
|-------|-----------|----------------|
| Skin registry | The 12 skin ids + parsing/defaults | [`apps/digichat/src/lib/thread-skins.ts`](../../apps/digichat/src/lib/thread-skins.ts) |
| Skin dispatch | id → React component | [`apps/digichat/src/components/assistant-ui/skins/index.tsx`](../../apps/digichat/src/components/assistant-ui/skins/index.tsx) |
| Skin implementations | The components themselves | `apps/digichat/src/components/assistant-ui/skins/` |
| Catalog page | Selector chrome + runtime | `apps/digichat/src/app/(baseline)/baseline/` |
| Backend | One BFF route, one upstream | `apps/digichat/src/app/api/baseline-chat/route.ts` |

First-party hosts and slugs (`digithings.ai`, `occ`, `digithings-ai`) already
default to the `digichat` skin via `defaultThreadSkinForTenant()`; third-party
tenants default to the catalog `base`. The gallery makes that choice visible
instead of deploy-time.

---

## The skin library

Ids 1–11 are vendored assistant-ui catalog templates; `digichat` is the
first-party Thread. All 12 are in the image — not a CDN switch.

| Skin id | Component | Source | Notes |
|---------|-----------|--------|-------|
| `base` | `Base` | `skins/base/thread.tsx` | Fixed Base demo (the default id) |
| `base-assistant-ui` | `ConfigurableBase` | `skins/base-assistant-ui/` | Same Thread inside the official `brandTheme` / labels shell |
| `chatgpt` | `ChatGPT` | `skins/chatgpt.tsx` | Clone skin |
| `claude` | `Claude` | `skins/claude.tsx` | Clone skin |
| `grok` | `Grok` | `skins/grok.tsx` | Clone skin |
| `gemini` | `Gemini` | `skins/gemini.tsx` | Clone skin |
| `perplexity` | `Perplexity` | `skins/perplexity.tsx` | Clone skin |
| `react-ink` | `ReactInkWeb` | `skins/react-ink.tsx` | Web facsimile of the terminal thread |
| `expo-react-native` | `ExpoReactNative` | `skins/expo-react-native.tsx` | Web facsimile of the Expo phone frame |
| `webpage-assistant` | `WebpageAssistant` | `skins/webpage-assistant/` | Owns the page chrome (`LAYOUT_SKINS`) |
| `product-page-assistant` | `ProductPageAssistant` | `skins/product-page-assistant/` | Owns the page chrome; also the fallback branch |
| `digichat` | `DigichatSkin` | `skins/digichat.tsx` | First-party Thread from the shared UI package (`@digithings/ui/chat/thread`) |

Registry helpers: `THREAD_SKINS`, `DEFAULT_THREAD_SKIN` (`"base"`), `CLONE_SKINS`,
`LAYOUT_SKINS`, `isCloneSkin()`, `skinOwnsPageChrome()`, `parseThreadSkin()`.
`parseThreadSkin()` never throws — an unknown value falls back to the default.

---

## One backend for every skin

The browser talks to a BFF route; the BFF talks upstream. No key ever reaches the
browser.

```
browser (any skin)
  └─ useChatRuntime + AssistantChatTransport   →  POST /api/baseline-chat
                                                      └─ upstream chat BFF
```

- The client runtime is built once in `baseline-client.tsx` and shared by every
  skin, so switching skins never rebuilds the transport.
- `app/api/baseline-chat/route.ts` proxies the upstream, forwarding
  `x-digi-run-id` and `x-digichat-session`, and setting the `x-embed-host` /
  `origin` / `referer` / `user-agent` headers the upstream expects.
- The upstream is pinned in `apps/digichat/src/lib/baseline-preview.ts`
  (`BASELINE_DEFAULT_UPSTREAM` = `https://digithings.ai/api/chat`).
  `DIGICHAT_BASELINE_UPSTREAM` can override it, but only to that exact
  https host+path — anything else **fails closed** to the default (no
  user-controlled SSRF).
- The route is gated by `isLocalBaselinePreview()`: it returns 404 unless the
  build is non-production **and** the request host is `127.0.0.1` / `localhost`.
  That loopback+dev gate is why it is one of the few `src/app/api/` routes that
  does not call `requireDigiChatAuth()` (with `health`, `deploy/chrome`,
  `embed/tenant-config`, `mcp/oauth/callback` and `plan-proof`) — it is not a
  public API.

To point the gallery at a **different** backend (a local Python stack, a staging
host), change the upstream resolution in `baseline-preview.ts` or the proxy in
`route.ts`. Do not add the upstream URL to the client.

---

## Selector chrome

`apps/digichat/src/app/(baseline)/baseline/baseline-client.tsx` renders:

- a **top bar** of skin links built from `THREAD_SKINS` (so a newly registered
  skin appears automatically), plus a **light/dark toggle** on the right;
- the selected skin via `<ThreadSkinView skin={skin} />`.

URL contract: `?skin=<id>&theme=dark` (theme omitted means light; `skin` omitted
means the default). Links carry both, so any state is shareable.

The theme is applied to `<html>` — `documentElement.dataset.theme` plus a
`.light` / `.dark` class. This is load-bearing: the first-party theme's light
palette hangs off `:root[data-theme="light"] .digichat-thread` and its portal
mirrors off `html.light:has(...)`. Without it the `digichat` skin renders its
dark palette even in "light" mode.

---

## Testing the full feature set

The gallery is wired to exercise the product's real feature surface, not a
stub — tools, menus, tool-call chains, reasoning, attachments.

**Chat prefs host.** `baseline-client.tsx` mounts the same prefs host the
embed and product shells use:

```tsx
const { prefsApi, panes } = useStockChatPrefs({
  clientConfig: DEFAULT_CLIENT_CONFIG,
  sessionKey: "baseline",
  hasSessions: false,
  newThread: noop,
  redo: noop,
});
// …
<StockChatPrefsHost value={prefsApi} panes={panes}>
  <ThreadSkinView skin={skin} />
</StockChatPrefsHost>
```

`useStockChatPrefs` / `StockChatPrefsHost` live in
`apps/digichat/src/components/stock/stock-chat-prefs-host.tsx` and build a full
`EmbedChatPrefsApi` with no sign-in. This is what turns on the `digichat` skin's
composer chrome: the `/` command palette (19 commands — `/new`, `/clear`,
`/compact`, `/undo`, `/redo`, `/copy`, `/export`, `/help`, `/settings`, `/view`,
`/thinking`, `/effort`, `/models`, `/language` and language shortcuts), the
settings/tools/model panes, and the `@`-mention menu.

**Tool catalog.** `DEFAULT_CLIENT_CONFIG`
(`apps/digichat/src/lib/deploy-config/client-projection.ts`) deliberately ships
`tools.catalog: []` and `mcp.servers: []` — the least-privilege unconfigured
fallback. The `/` palette works without them, but the `@`-mention menu, tool
chips, and tool-call chains stay empty. To exercise those, pass a config with a
populated catalog (or a deploy YAML through `toDigichatClientConfig()`); the
prefs host reads `catalogToolsFromClient()` and the skin renders the resulting
tool calls.

**Per-skin feature flags.** Attachments, dictation, speech, model picker, branch
picker, sources, reasoning/tool disclosure modes all come from the config
(`features`, `gate`) and the skin's own `useDisclosureUi` wiring — so a config
change is enough to test a feature across skins without touching a component.

---

## Adding or changing a skin

**Modify an existing skin:** edit its component under
`apps/digichat/src/components/assistant-ui/skins/`. The gallery picks it up
immediately (HMR); nothing else to register.

**Add a new skin:**

1. Create the component at
   `apps/digichat/src/components/assistant-ui/skins/<id>.tsx` (or a directory,
   if it ships several files).
2. Add the id to `THREAD_SKINS` in
   `apps/digichat/src/lib/thread-skins.ts` (lowercase, dashes).
3. Add its branch to `ThreadSkinView` in `skins/index.tsx` — or to
   `CLONE_THREADS` if it is a clone-skin variant. Note the final `return` is the
   `ProductPageAssistant` fallback, so an unregistered id silently renders that;
   register it explicitly.
4. If the skin owns the whole page (docs shell, product dashboard, device
   frame), add it to `LAYOUT_SKINS` so host chrome does not wrap it.
5. That is the whole registration — the top bar iterates `THREAD_SKINS`, so the
   new skin appears in the selector with no UI change.
6. Keep the skin tests green (`skins/index.test.tsx`,
   `skins-isolation.test.ts`) and note provenance in
   `apps/digichat/src/components/assistant-ui/skins/SOURCE.md`.

---

## Branding credit + surface parity

The `digichat` skin renders one shared branding line below the composer on
every surface (catalog, product, embed): `SkinCredit`
(`packages/ui/src/components/chat/stock/skin-credit.tsx`) — `powered by
digichat — a digithings product.`, with `digithings` linked to
https://digithings.ai. It is a watermark, not a disclaimer: always visible,
empty thread included. It returns null only when the host opted out
(`chrome.attribution: false` / embed `attribution: false`).

Placement rule: in-flow inside the sticky viewport footer once messages
exist; a click-transparent absolute bottom pin in empty states whose
composer floats mid-page (the clones, stock Thread, base). The gallery
Thread (the `digichat` skin itself) needs no pin — its footer is
bottom-docked in every state, so in-flow is already bottom-pinned there; an
overlay painted over the composer. Send controls pin themselves right with
`ml-auto`, so the submit stays right even when the deployment disables
attachments and the attach button is absent.

Parity rule: the skin owns all footer/composer geometry (footer `pb-4
md:pb-6` halved to `pb-2 md:pb-3` alongside the credit's own `pt-0.5`,
composer layout). Hosts must not override it per surface — the embed and
catalog shells each once collapsed the footer padding and forked the footer
position three ways. Two isolation tests pin this (`baseline-isolation`,
`product-isolation`: no host `.aui-thread-viewport-footer` padding rules).

Composer layout default is `expanded` on every surface
(`composerLayout ?? "expanded"` in `skins/digichat.tsx`); `compact` is an
explicit per-deployment override, not a mode derivation.

---

## Gotchas that make a skin render wrong

The catalog page is deliberately isolated: its own root layout and
`app/(baseline)/baseline.css`, **no** digichat `globals.css`, tokens, or CLI
skin. That isolation is what keeps the catalog honest, but it means a skin can
render subtly wrong with no error. These five have each caused a real bug:

1. **The skin scope marker.** The first-party theme in
   `packages/ui/src/styles/chat-digichat.css` is scoped to
   `:is(.aui-theme-stage, [data-thread-skin="digichat"])` and its portal rules to
   `html:has([data-thread-skin="digichat"])`. The gallery Thread root declares
   `data-thread-skin="digichat"` itself, which is why `/baseline`, `/embed` and
   production all render the same theme. A new skin that wants that theme must
   declare the marker too.
2. **Tailwind `@source` must reach `packages/ui`.** Tailwind only emits
   utilities it can see. `baseline.css` therefore has an `@source` line for
   `packages/ui/src/components/chat`; without it kit-only utilities are dropped
   and you get silent visual bugs (the tooltip arrow suppression regressed into
   a visible diamond under every hover label).
3. **The font variable.** The `digichat` theme resolves
   `--font-geist-mono`. If it is undefined the whole `font-family` declaration
   is invalid and the skin falls back to the page font — so the catalog root
   layout loads `Geist_Mono` even though it is otherwise isolated.
4. **The prefs host.** No `EmbedChatPrefsProvider` above the skin means
   `useEmbedChatPrefsOptional()` returns `null`, `enableSlash` is false, and the
   `/` palette plus `@`-mentions are silently absent.
5. **The theme attribute.** See "Selector chrome" — `data-theme` / `.light` on
   `<html>` is what makes the first-party light palette match.

Machine-readable version of this list: `src/lib/thread-skin-host-contract.ts`
(`DIGICHAT_SKIN_HOST_CONTRACT`, pinned by `thread-skin-host-contract.test.ts`).
A new host must satisfy every item there before a skin can render correctly.

---

## Porting the gallery to another deployment

The gallery is four files plus one route. Copy, then change the route and the
upstream:

| File | Role |
|------|------|
| `app/(baseline)/layout.tsx` | Isolated root layout + font variables |
| `app/(baseline)/baseline.css` | Tailwind + tokens + `@source` set |
| `app/(baseline)/baseline/page.tsx` | Dev gate (`notFound()` in production) |
| `app/(baseline)/baseline/baseline-client.tsx` | Selector chrome, runtime, prefs host, theme |
| `app/api/baseline-chat/route.ts` + `lib/baseline-preview.ts` | The single backend |

To change what the gallery targets: swap the upstream in
`baseline-preview.ts`, or replace the proxy body in `route.ts` with your own
BFF call. Keep the loopback/dev gate unless you are deliberately making it a
public surface — that would be new external network exposure and needs a human
decision.

---

## Where to look

| Question | File |
|----------|------|
| What skins exist, what is the default? | `apps/digichat/src/lib/thread-skins.ts` |
| Which component renders skin X? | `apps/digichat/src/components/assistant-ui/skins/index.tsx` |
| Where is the catalog page / selector? | `apps/digichat/src/app/(baseline)/baseline/baseline-client.tsx` |
| Where is the backend wired? | `apps/digichat/src/app/api/baseline-chat/route.ts`, `apps/digichat/src/lib/baseline-preview.ts` |
| Where do tools / menus / features come from? | `apps/digichat/src/components/stock/stock-chat-prefs-host.tsx`, `apps/digichat/src/lib/deploy-config/client-projection.ts` |
| Where does the first-party theme live? | `packages/ui/src/styles/chat-digichat.css`, `packages/ui/src/styles/chat-aui.css` |
| Skin provenance / vendored sources | `apps/digichat/src/components/assistant-ui/skins/SOURCE.md` |

Related: [`STOCK-SMOKE.md`](STOCK-SMOKE.md) (manual checklist on the product
`/embed` path), [`DESIGN-THEMES.md`](DESIGN-THEMES.md) (theme tokens),
[`INSTALL.md`](INSTALL.md) (deploy config).
