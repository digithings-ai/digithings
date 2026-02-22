# Digi Architecture – High-Level Design (February 2026)

(See `DIGI.md` Section 3 for full narrative.)

```mermaid
graph TD
    User[User / Small Firm Chat] --> DigiClaw[DigiClaw\nOpenClaw Runtime + MCP Gateway + Heartbeat]
    DigiClaw <--> DigiGraph[DigiGraph\nLangGraph + Layered Agent Families + GraphRAG]
    DigiGraph <--> DigiQuant[DigiQuant Pack\nNautilusTrader + Polars + VectorBT Pro + Qlib/FinRL]
    DigiQuant <--> External[External\nPolygon • IB • Alpaca • QuantConnect • TradingView]
    DigiGraph --> Memory[Persistent Strategy Memory\nNeo4j + Graphiti + PGVector]
    DigiClaw --> SelfHealing[Self-Healing Loop\nMonitoring Agent + ADDM Drift Detection]
```

Key Interfaces (strictly MCP-first)

DigiClaw exposes one custom skill: run_digigraph_workflow
DigiGraph exposes every major node (research, backtest, optimize, ML family) as discoverable MCP tools
All data exchange uses structured Pydantic models + Arrow zero-copy where possible
No direct user exposure to DigiQuant — it is a plug-in pack only

Component Responsibilities (cross-reference sub-folder docs)
Component,Primary Role,Calls / Receives From
DigiClaw,"User gateway, runtime, monitoring",User ↔ DigiGraph
DigiGraph,Cognitive orchestration & memory,DigiClaw ↔ DigiQuant
DigiQuant,High-perf research → backtest → live,DigiGraph only

Token efficiency: LiteLLM caching + local models for routine tasks
Compute efficiency: Rust/Polars/Nautilus only (no pandas)
Security: loopback-only, Tailscale, least-privilege (see SECURITY.md)
Scalability: Docker Compose → Kubernetes-ready, one instance per small firm

This diagram and the sub-folder documents together form the complete architectural source of truth.