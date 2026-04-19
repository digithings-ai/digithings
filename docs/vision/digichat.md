# DigiChat

> The conversational interface for every DigiThings deployment — your models, your keys, your data.

**What it is:** DigiChat is the client-facing chat interface that powers every DigiThings deployment. It is a Next.js application with a backend-for-frontend layer that connects to DigiGraph for agent orchestration. Two core principles define it: (1) bring your own keys — users supply their own LLM provider API keys and pay their own compute costs; (2) adaptive UI — the interface surfaces only what the user has access to based on their DigiKey permission scope.

**The problem:** Most AI chat interfaces are locked to one model provider and one use case. Switching providers means switching platforms. Adding new data sources or tools means custom integration work. DigiChat inverts this — the orchestration and tooling are DigiThings, the compute and data are the user's own.

**BYOK model selector — core feature:**
A settings panel where users configure their LLM backend: API key input, provider selection (OpenAI, Anthropic, Gemini, Ollama, and others), optional OAuth login for providers that require it. Keys persist in the DigiChat Drizzle/Postgres store today, and migrate to DigiStore once that module ships. LiteLLM translates any provider into one standardized API language — translation only, not routing intelligence. The user pays their provider directly. DigiThings provides the orchestration, tooling, and graph layer.

**Adaptive UI driven by DigiKey JWT scopes:**
DigiChat reads the user's JWT on login and shows only what they're authorized to use. If a scope is absent, the feature doesn't appear — not locked, not visible.

Examples:
- digiquant:read → DigiQuant tools available as chat connections
- index:research → Research library DigiSearch index available
- subgraph:atlas → Atlas research sub-graph accessible
- tier:free → 3 questions, public index only, no proprietary sub-graphs

**Two live deployments:**

digithings.ai — platform demo:
DigiThings own documentation indexed. Free tier: 3 questions with a cheap fast model. BYOK to continue beyond free. Model selector spans OpenAI, Anthropic, Gemini, Ollama. Sample questions displayed to guide exploration ("What does DigiQuant do?"). Goal: let any visitor experience the DigiThings stack directly.

digiquant.io — investment profiling:
Entry flow powered by a proprietary investment profiling sub-graph. User inputs investment preferences → DigiChat builds and saves an investment profile to DigiStore (user acquisition + personalization). Shows what strategies and allocations could be constructed for their profile. Paywall trigger: "Ready to build your first strategy? Start with Kairos." Free taste → paid conversion.

**Enterprise deployments (client pattern):**
A client organization deploys DigiChat pointed at their own DigiSearch index. Users log in via their corporate SSO (Microsoft, Google) — DigiKey identifies them, maps them to their organization's project, and issues a JWT with the appropriate index and tool scopes. The UI adapts: only their organization's indexes and approved tools appear. Index results are filtered by user access level.

**Current state (shipped):**
Next.js BFF + React UI, Auth.js sessions, Drizzle ORM, AI SDK, Postgres for conversation history, BYOK UI flow live, deployed to chat.digithings.ai.

**12-month roadmap:**
- Model selector settings panel (full provider list, BYOK per provider)
- Investment profiling sub-graph (digiquant.io entry flow)
- Microsoft SSO and Google OIDC login via DigiKey
- Adaptive UI: scope-driven connection visibility
- digithings.ai demo instance (docs indexed, 3-question free tier)
- User conversation history and session management
- Kairos strategy exploration interface

**Open source vs. proprietary:** DigiChat application — open. Proprietary sub-graphs that power specific chat flows (investment profiling, Atlas research interface) — commercial.
