# Contributing to the Digi Ecosystem

**Version 1.0** | **February 20, 2026** | **Status: Living Source of Truth**

Thank you for contributing to the autonomous quant desk of 2026.  
All agents must read AGENTS.md first, then return here. 
For humans that dared, please follow the rules bellow.

## Required Reading Order (every contributor)
1. `README.md` (this repository overview)  
2. `DIGI.md` (master vision & business strategy)  
3. `ARCHITECTURE.md` (high-level diagrams & interfaces)  
4. `ROADMAP.md` (current phase)  
5. The specific sub-folder document for the component you are working on (`digiclaw/DIGICLAW.md`, `digigraph/DIGIGRAPH.md`, or `digiquant/DIGIQUANT.md`)  
6. This `CONTRIBUTING.md`

## Hard Rules (non-negotiable)
- **MCP-first** — Every new capability must be exposed as a discoverable MCP tool  
- **No pandas** — Use Polars exclusively for all data work  
- **NautilusTrader core** — All backtesting, optimization, and live execution must use Nautilus Actors  
- **Token efficiency** — LiteLLM caching + structured Pydantic outputs mandatory  
- **Dockerized** — Every component must run via the root `docker-compose.yml`  
- **Layered supervisor pattern** — All agent logic in DigiGraph follows the supervisor + sub-graph architecture  
- **Security** — Follow every rule in `SECURITY.md` (least privilege, human gates, audit logging)

## Code Style & Structure
- Python 3.12+ with strict type hints  
- All LLM outputs use Pydantic models (no raw strings)  
- File layout must match the component’s existing structure  
- Add/update the relevant section in the sub-folder `DIGIxxx.md` when introducing new features

## Workflow for Coding Agents
1. Receive a task that references a specific section of this document suite.  
2. Implement **only** what is asked while staying aware of the full ecosystem.  
3. Include inline comments referencing the relevant `DIGI.md` / architecture section.  
4. Submit a pull request with:
   - Updated documentation if interfaces change  
   - New/updated tests in `tests/`  
   - Docker Compose changes (if any)

## Human Contributor Workflow
1. Create a branch `feature/description`  
2. Open a PR with clear description and links to the sections you modified  
3. Request review from the lead maintainer (or your assigned agent swarm)

## Testing Requirements
- Unit tests for every new MCP tool and LangGraph node  
- End-to-end test: “chat idea → backtest → cached strategy” must pass  
- Performance test: 10 M-row Nautilus backtest < 2 seconds

## Questions or Ambiguity
- Default to the most conservative, secure, and token-efficient option  
- If unclear, open an issue referencing the exact section of `DIGI.md` or `ARCHITECTURE.md`

By contributing you agree to uphold the vision in `DIGI.md` and the technical constraints defined in this document suite.

Welcome to building the future of agentic quantitative finance.