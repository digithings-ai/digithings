# digichat configurable chat experience — brainstorm (not a spec)

> Captured verbatim-intent from a dictated brainstorm during the BYOK provider/model
> catalog work (Plan A/B). Explicitly deferred by the user to a separate session —
> "Plan C." Nothing here has been evaluated for feasibility, scoped, or planned.
> Do not start implementation from this file directly — run it through
> brainstorming/writing-plans first.

## Core idea

Let users pick a different underlying model **without providing their own API key** —
i.e. an operator-funded model *selection*, not just BYOK. Today digichat's non-BYOK
default is a single fixed model (DeepSeek via OpenRouter). The ask is to offer a
curated set of alternatives around the same capability/price band as the current
default, so users get real choice without the operator's per-message cost rising.

- Keep OpenRouter as the default client/transport.
- Expand the *default* (non-BYOK) roster beyond one model: more open-source options,
  maybe some flagship options, possibly smaller/cheaper ones too — the one hard
  constraint is **price parity with DeepSeek** (or at least "capable but affordable,"
  explicitly so the operator's cost per chat doesn't rise).
- This is a distinct concern from Plan A's BYOK tiering (free/opensource/flagship for
  *bring-your-own-key* OpenRouter users) — this is about the *no-key* default path.

## Interaction model: slash commands

- `/model` — opens a picker to switch the active (non-BYOK) default model for the
  session, from the curated affordable roster above.
- `/byok` (the user said "b-o-y-k" / "bring your own key") — opens the existing BYOK
  key-entry flow from mid-conversation, without needing to leave/restart the session.
- General pattern: more slash commands over time for anything that changes chat
  *behavior* without changing which model answers — the user was explicit that
  "for now, we'll keep to modifying the model" for the first cut, and views broader
  behavior-modifying commands as a natural follow-on, not part of the first slice.
- Longer-term aspiration: a general `/config`-style menu (compared explicitly to how
  CLI coding agents expose a settings menu) that surfaces "anything that can be
  configured that doesn't drastically change the model" in one place, rather than
  one command per setting.

## Other configurability ideas mentioned (lower priority / later)

- **Trace/tool-call verbosity view mode**: expand-by-default (show full chain +
  sources) vs. compact-by-default (show only the names of tools called). A per-session
  or per-user toggle for how much of the agent's reasoning/tool chain is visible.
- **Output style / response prompt customization**: let a user supply their own
  "preference for the prompt and style of the response" for that session — i.e.
  session-scoped prompt/style injection, ingested from user input rather than
  hardcoded.

## Stated motivation

The user wants digichat to showcase what a "bring-your-own-token style chatbot" can
be: configurable and modular, not just a single fixed default experience. Cost control
for the operator (self-funded default tier) is an explicit, recurring constraint
throughout — every expansion of the free/default roster is bounded by "same price as
what we already run at."

## Explicit deferral

The user asked for this to be brainstormed in a **parallel/separate session**
specifically so it would not interrupt the BYOK provider/model catalog work in
progress, with the intent to turn it into a "Plan C" once that's ready. Treat this
file as raw brainstorm input for that future brainstorming/spec/plan cycle — not
as anything to act on now.
