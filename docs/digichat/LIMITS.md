# digichat limits

One YAML block, `limits`, configures every gate a digichat deployment can
turn on. Omit the block and nothing is enforced. A gate that is present
combines with the others by AND: every gate must pass, and the first one
that is already exceeded wins.

`guardrails` is the alias of two of these gates (token-per-minute pause and
the per-turn tool cap). New configs should use `limits`. If both are set
they must name the same max for the same path.

The checker lives in the BFF. It does not call a model. Counters are
per Node process, same as the token window: two instances do not see each
other's spend until a host installs a shared store.

`perMinute`, `perHour`, and `perDay` are rolling windows (60s, 3600s, 86400s),
matching the token-window waiter and `models.costPerWindow`. They are not
calendar buckets. A session window lasts for that conversation. A concurrent
session slot lasts until `idleMinutes` (default 30) with no further turn.

## Order

The first hit wins:

1. `limits.sessions`
2. `limits.turns`
3. `limits.models`
4. `limits.cost`
5. `limits.tokens`
6. `limits.toolCalls` (inside the turn, not before it)

## Actions

| `onExceed` | What the BFF does |
|---|---|
| `block` | `429` `limit_exceeded` and the configured message. The model is not called. |
| `fallback-auto` | The turn continues on `models.default` (the Auto model). |
| `pause` | The turn continues once, with a notice, and the model is told to summarize and stop. Token-per-minute `pause` uses the existing rolling-window waiter instead of a pre-check. |

Defaults when `onExceed` is omitted: tokens and tool calls `pause`, model tier `fallback-auto`, everything else `block`.

An unknown client IP skips IP-scoped gates. It is not an identity.

## Paths

```yaml
limits:
  combine: all                    # the only combination
  onUnsupported: reject           # or warn. Default reject.
  tokens:
    input:                        # or output, or total
      perMinute:                  # or perHour, perDay, perSession
        deployment:               # or subscription, user, ip, session
          max: 80000              # positive integer, up to 10000000
          answerAt: 0.7           # token gates only. Default 0.7 when set.
          pauseAt: 0.9            # must be above answerAt
          onExceed: pause
          message: optional notice
  cost:
    usd:
      perDay:
        user:
          max: 0.0125565          # USD. premiumOnly meters premium models only.
          premiumOnly: true
          onExceed: fallback-auto
    prices:                       # USD per million tokens. Overrides the catalog.
      openai/gpt-6.1-sol:
        inputPerM: 1.5
        outputPerM: 7.77
  turns:
    perSession:                   # or perMinute, perHour, perDay
      session:                    # or deployment, subscription, user, ip
        max: 12
        onExceed: block
  sessions:
    perIp:
      max: 1
      window: concurrent          # or minute, hour, day. Default concurrent.
      idleMinutes: 30             # concurrent slots only. Default 30.
      onExceed: block             # pause is rejected
  toolCalls:
    perTurn:                      # perQuestion is the same gate. Set only one.
      max: 20
      onExceed: pause             # fallback-auto is rejected
  models:
    standard:
      maxOutputUsdPerMillion: 2   # must match models.priceCapUsdPerMillion
    premium:
      manualOnly: true
      ids: []                     # optional explicit premium ids
      onExceed: fallback-auto
```

`models.priceCapUsdPerMillion` is the catalog picker's cap (the #6193 key).
`limits.models.standard.maxOutputUsdPerMillion` is the same number. When both
are set they must be equal. `models.premiumCapUsdPerMillion` is that picker's
upper premium cap. Auto, the presets, and the router stay on the standard
tier in that picker. A model whose output price is above the standard cap, or
whose id is listed under `premium.ids`, is premium. With `manualOnly: true`
an implicit pick of a premium model takes `onExceed`. An explicit pick is
allowed and spends `limits.cost` at that model's price, so a pricier model
uses the budget faster.

`models.costPerWindow` is the #6193 spelling of one premium cost gate: per
user, `premiumOnly`, `onExceed: fallback-auto`. `windowSeconds` of 60, 3600,
or 86400 is `perMinute`, `perHour`, or `perDay`. Any other positive integer
is a rolling window of that many seconds. When `limits.cost.usd` already has
that named window for `user`, the two must name the same max and the limits
gate must set `premiumOnly: true` — one counter, not two. A standard-tier
model does not spend a `premiumOnly` budget.

Prices come from `limits.cost.prices` and, when the file is present, from
`config/model-picker-catalog.json` (`inputPerM` / `outputPerM`). This tree
does not vendor that file. A model with no price and not listed in
`premium.ids` is not treated as premium.

User scope uses a real user id, otherwise the session id, otherwise the
client IP. `embed:anonymous` is not a person.

## Backend matrix

`reject` (the default) fails config load. `warn` drops the gate and stores
the reason on `limits.warnings`. Nothing unsupported is silently kept.

| Backend | Tokens | Cost | Turns | Sessions | Tool calls | Model tiers |
|---|---|---|---|---|---|---|
| digigraph | enforce | enforce | enforce | enforce | enforce | enforce |
| langgraph | best-effort | best-effort | enforce | enforce | best-effort | enforce |
| openai-completions, openai-responses, anthropic, google-vertex | enforce | enforce | enforce | enforce | enforce | enforce |
| foundry (Azure AI Foundry agent) | partial | unsupported | enforce | enforce | enforce | unsupported |
| ag-ui | unsupported | unsupported | enforce | enforce | best-effort | unsupported |
| a2a | unsupported | unsupported | enforce | enforce | unsupported | unsupported |

Foundry partial means total tokens per minute at `deployment` or
`subscription` scope only. Input, output, per-user, per-IP, per-session, and
any window other than a minute are rejected. The deployment does not choose
the model, so cost and model tiers are rejected too. Tool calls, turns, and
session or IP gates are enforced in the BFF.

digigraph tool calls are enforced, not best-effort: `POST /api/chat` forwards
the cap as `X-Digi-Max-Tool-Calls`, digigraph shares that one budget across the
turn's main loop and its continuations, and digillm stops at that many executed
calls and answers tool-free. Nothing is shown in the UI. LangGraph tool calls
stay best-effort: the upstream loop is not aborted, and the BFF sends a
wrap-up on the next round it can see. LangGraph token and cost settlement is
best-effort because that stream does not report usage. AG-UI has no usage channel and no model pick, so tokens, cost, and
model tiers are rejected. Its tool-call cap is an instruction on the one
request, not an abort. A2A does not expose countable tool calls, so that gate
is rejected. Turns and sessions are counted in the BFF on every backend.

## Examples

None of these blocks are enabled in the shipped YAML. They are the shapes an
operator would uncomment.

### digithings.ai public

House backend. Standard tier at $2 per million output tokens, matching the
catalog cap. `models.costPerWindow` is the premium budget from the model
picker: three typical turns of the pricier premium model (about 3,550 input
tokens and 600 output tokens) per rolling day. The figure is that budget,
not a live quote. The per-user token pause is the public-chat bot gate.
The same budget written as `limits.cost` is shown underneath; set one of them.

```yaml
models:
  priceCapUsdPerMillion: 2
  premiumCapUsdPerMillion: 2.5
  costPerWindow:
    usd: 0.0125565
    windowSeconds: 86400
limits:
  combine: all
  tokens:
    total:
      perMinute:
        user:
          max: 80000
          onExceed: pause
  models:
    standard:
      maxOutputUsdPerMillion: 2
    premium:
      manualOnly: true
      onExceed: fallback-auto
```

Equivalent cost gate, if the deployment does not set `models.costPerWindow`:

```yaml
limits:
  cost:
    usd:
      perDay:
        user:
          max: 0.0125565
          premiumOnly: true
          onExceed: fallback-auto
          message: You've used today's premium budget. Answering with Auto instead.
```

### OCC

Same standard tier. No session-per-IP gate: an office network shares an
address, and one slot would lock the tenant. A daily question cap and a tool
cap sit in front of a premium cost budget. The model-picker config leaves
OCC's `costPerWindow` unset, so this block is the operator's choice, not a
budget that is already turned on.

```yaml
models:
  priceCapUsdPerMillion: 2
limits:
  combine: all
  turns:
    perDay:
      user:
        max: 40
        onExceed: block
        message: The question limit for today has been reached.
  toolCalls:
    perTurn:
      max: 8
      onExceed: pause
  cost:
    usd:
      perDay:
        user:
          max: 0.25
          premiumOnly: true
          onExceed: fallback-auto
  models:
    standard:
      maxOutputUsdPerMillion: 2
    premium:
      manualOnly: true
      onExceed: fallback-auto
```

### Foundry trial on Azure

Foundry agent. The model is the agent's model. Cost and model tiers are
rejected. One live chat per IP, a per-turn tool cap, a daily question cap,
and the deployment TPM once the Azure number is known. `100000` below is an
illustration, not the live quota.

```yaml
backend:
  type: foundry
limits:
  combine: all
  sessions:
    perIp:
      max: 1
      window: concurrent
      idleMinutes: 30
      onExceed: block
      message: This trial allows one chat at a time from your network.
  toolCalls:
    perTurn:
      max: 5
      onExceed: pause
  turns:
    perDay:
      ip:
        max: 40
        onExceed: block
  tokens:
    total:
      perMinute:
        deployment:
          max: 100000
          onExceed: pause
```

`guardrails.maxToolCallsPerTurn` and `guardrails.tokensPerMinute.deployment`
are the alias of the tool cap and the deployment TPM. `backend.maxToolCalls`
on Foundry is still that tool cap. The shared `limits` key wins when both
shapes are set to different numbers: config load fails.
