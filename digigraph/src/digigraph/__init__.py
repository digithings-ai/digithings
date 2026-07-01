# DigiGraph – LangGraph orchestration brain (Digi Ecosystem).
# See digigraph/ARCHITECTURE.md. MCP-first; supervisor + sub-graph in Phase 1+.

from digigraph.project_config import DigiProjectConfig, load_project_config

__version__ = "0.1.0"

__all__ = ["DigiProjectConfig", "load_project_config", "__version__"]
