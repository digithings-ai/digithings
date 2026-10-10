#!/usr/bin/env python3
"""One-time authoring aid for config/contract/contract.yaml.

The generated file is CHECKED IN and is the source of truth. This script exists
so the mechanical half of it (which worker declares a var, which compose
service interpolates a name) is transcribed once by a parser instead of by a
human reading TOML. Re-run it only when deliberately re-baselining; the
acceptance check is config/contract/check_contract.py, not this script.
"""

from __future__ import annotations

import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).resolve().parent / "contract.yaml"

COMPOSE_FILES = ["docker-compose.yml", "apps/digitrace-langfuse/docker-compose.local.yml"]
ENV_EXAMPLE_FILES = [".env.example", "apps/digichat/.env.example"]
# Files under docs/templates are project scaffolding, not this stack.
DOCS_TEMPLATE_PREFIX = "docs/templates/"


def strip_yaml_comments(text: str) -> str:
    """Remove full-line and trailing comments, quote-aware.

    The root compose carries a `${VAR:?}` example inside a `#` comment; a
    comment-blind scan would demand a contract entry for a variable that does
    not exist.
    """
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            out.append("")
            continue
        quote = None
        buf = []
        for i, ch in enumerate(line):
            if quote:
                buf.append(ch)
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
                buf.append(ch)
            elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
                break
            else:
                buf.append(ch)
        out.append("".join(buf))
    return "\n".join(out)


def compose_env_names() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for rel in COMPOSE_FILES:
        text = strip_yaml_comments((ROOT / rel).read_text())
        for match in re.finditer(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", text):
            found.setdefault(match.group(1), set()).add(rel)
    return found


def compose_literal_env_names() -> set[str]:
    """Literal (non-interpolated) `KEY: value` env entries, quoted-aware."""
    names: set[str] = set()
    for rel in COMPOSE_FILES:
        text = strip_yaml_comments((ROOT / rel).read_text())
        for match in re.finditer(
            r"^\s+-\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?!\$)", text, re.MULTILINE
        ):
            names.add(match.group(1))
    return names


def env_example_names() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for rel in ENV_EXAMPLE_FILES:
        for line in (ROOT / rel).read_text().splitlines():
            if line.lstrip().startswith("#"):
                continue
            match = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            if match:
                found.setdefault(match.group(1), set()).add(rel)
    return found


def wrangler_inventory() -> tuple[dict, dict]:
    """Return ({worker: {var: value}}, {worker: [binding dicts]})."""
    vars_by_worker: dict[str, dict] = {}
    bindings: dict[str, list] = {}
    for path in sorted((ROOT / "apps").glob("*/wrangler.toml")):
        app = path.parent.name
        data = tomllib.loads(path.read_text())
        worker = data.get("name", app)
        vars_by_worker[worker] = dict(data.get("vars", {}))

        rows: list[dict] = []
        for container in data.get("containers", []) or []:
            rows.append(
                {
                    "type": "container",
                    "class_name": container.get("class_name"),
                    "image": container.get("image"),
                    "max_instances": container.get("max_instances"),
                    "instance_type": container.get("instance_type"),
                    "source": str(path.relative_to(ROOT)),
                }
            )
        durable = data.get("durable_objects", {}) or {}
        for binding in durable.get("bindings", []) or []:
            rows.append(
                {
                    "type": "durable_object",
                    "name": binding.get("name"),
                    "class_name": binding.get("class_name"),
                    "source": str(path.relative_to(ROOT)),
                }
            )
        for binding in data.get("r2_buckets", []) or []:
            rows.append(
                {
                    "type": "r2_bucket",
                    "name": binding.get("binding") or binding.get("name"),
                    "bucket_name": binding.get("bucket_name"),
                    "source": str(path.relative_to(ROOT)),
                }
            )
        for binding in data.get("services", []) or []:
            rows.append(
                {
                    "type": "service",
                    "name": binding.get("binding") or binding.get("name"),
                    "service": binding.get("service"),
                    "source": str(path.relative_to(ROOT)),
                }
            )
        bindings[worker] = rows
    return vars_by_worker, bindings


# --------------------------------------------------------------------------
# Authored metadata. `description` is required for every name; `secret` marks a
# value that must never be printed, logged or committed.
# --------------------------------------------------------------------------
SECRET = True
PLAIN = False

META: dict[str, tuple[str, bool]] = {
    # --- auth / digikey -------------------------------------------------
    "AUTH_SECRET": (
        "DigiChat session-signing secret. Never printed; rotate invalidates every session.",
        SECRET,
    ),
    "AUTH_TRUST_HOST": ("Trust the Host header for DigiChat URL building.", PLAIN),
    "AUTH_URL": ("DigiChat public auth origin.", PLAIN),
    "AUTH_OIDC_ISSUER": ("OIDC issuer for DigiChat SSO.", PLAIN),
    "AUTH_OIDC_CLIENT_ID": ("OIDC client id for DigiChat SSO.", PLAIN),
    "AUTH_OIDC_CLIENT_SECRET": ("OIDC client secret for DigiChat SSO.", SECRET),
    "DIGIKEY_JWKS_URL": ("JWKS endpoint every protected service fetches to verify JWTs.", PLAIN),
    "DIGIKEY_PUBLIC_KEY_PEM": ("Pinned digikey public key, used when JWKS is unreachable.", SECRET),
    "DIGIKEY_ISSUER": ("Expected `iss` claim. Must match the URL services fetch JWKS from.", PLAIN),
    "DIGIKEY_AUDIENCE": ("Expected `aud` claim for every digikey-issued token.", PLAIN),
    "DIGIKEY_BFF_TOKEN": ("Server-to-server token DigiChat uses to call digikey.", SECRET),
    "DIGIKEY_ADMIN_TOKEN": ("Optional digikey admin token for key management calls.", SECRET),
    "DIGIKEY_DATABASE_URL": (
        "digikey Postgres DSN. Required in the stack Worker; a sqlite path is the local default.",
        SECRET,
    ),
    "DIGIKEY_LITELLM_PROXY_KEY": (
        "digikey's key into LiteLLM; falls back to LITELLM_MASTER_KEY.",
        SECRET,
    ),
    "DIGIKEY_BLOCKLIST_REDIS_URL": ("Redis holding the JWT revocation blocklist.", PLAIN),
    "DIGIKEY_REQUIRE_BLOCKLIST": (
        "`1` refuses token issuance when the blocklist is unreachable (production default).",
        PLAIN,
    ),
    "DIGIKEY_ALLOW_EPHEMERAL_KEY": (
        "`0` in production; `1` only for local Docker via make stack-local.",
        PLAIN,
    ),
    "DIGIKEY_ALLOW_DEV_GLOBAL": ("Allows one global dev key. `0` in production.", PLAIN),
    "DIGIKEY_URL": ("Base URL clients use to reach digikey.", PLAIN),
    "DIGICLAW_DIGIKEY_API_KEY": ("Long-lived API key the digiclaw heartbeat agent uses.", SECRET),
    "DIGIGRAPH_UPSTREAM_API_KEY": ("digigraph's credential for its own upstream LLM.", SECRET),
    "E2E_BEARER_TOKEN": ("Bearer token for end-to-end test runs.", SECRET),
    # --- llm / routing ---------------------------------------------------
    "DIGI_LLM_MODE": ("LiteLLM routing mode. `test` keeps local runs off paid upstreams.", PLAIN),
    "OPENAI_API_KEY": ("OpenAI credential.", SECRET),
    "OPENROUTER_API_KEY": ("OpenRouter credential.", SECRET),
    "XAI_API_KEY": ("xAI credential.", SECRET),
    "OLLAMA_API_KEY": ("Credential for a non-local Ollama endpoint.", SECRET),
    "LITELLM_MASTER_KEY": ("LiteLLM master key. An empty value makes litellm exit 3.", SECRET),
    "LITELLM_PROXY_API_KEY": ("Credential services present to LiteLLM as a proxy.", SECRET),
    "OMNIROUTE_API_KEY": ("Omniroute credential.", SECRET),
    "OMNIROUTE_AUTH_PASSWORD": ("Omniroute auth-guard password.", SECRET),
    # --- digisearch / digivault / digiquant ------------------------------
    "DIGISEARCH_INDEX": (
        "digisearch collection name. Must agree across ingest, backfill and query.",
        PLAIN,
    ),
    "DIGISEARCH_EMBEDDING_PROVIDER": (
        "Embedding model id. All three call sites must agree exactly (384 dims) or retrieval silently misses.",
        PLAIN,
    ),
    "DIGISEARCH_URL": ("digisearch base URL as seen from its caller.", PLAIN),
    "DIGISEARCH_SEARXNG_URL": ("SearxNG endpoint digisearch calls for web search.", PLAIN),
    "DIGIVAULT_URL": ("digivault base URL as seen from its caller.", PLAIN),
    "DIGIVAULT_ROOT": ("digivault storage root inside the container.", PLAIN),
    "DIGIQUANT_URL": ("digiquant base URL. Empty in the chat-only Profile A deployment.", PLAIN),
    "DIGIQUANT_MARKET_DATA_BACKEND": (
        "`r2` makes containers read the R2 market seam; `127` drops the Supabase tables.",
        PLAIN,
    ),
    "DIGITRACE_URL": ("digitrace base URL. Empty in the chat-only Profile A deployment.", PLAIN),
    "ZAMMAD_BASE_URL": ("Zammad desk base URL for the read-only ticketing MCP.", PLAIN),
    "CHROMA_PATH": ("Chroma persistence directory inside the container.", PLAIN),
    # --- cron / runner ---------------------------------------------------
    "BACKFILL_ENABLED": (
        "`0` keeps POST /backfill returning 404; `1` exposes a production-writing surface.",
        PLAIN,
    ),
    "DRY_RUN": ("`1` makes cron jobs compute without writing.", PLAIN),
    "GITHUB_OVERRIDE_JOBS": (
        "Comma-separated job ids that regain workflow_dispatch. Empty means none.",
        PLAIN,
    ),
    "CLOUDFLARE_EMAIL_API_TOKEN": (
        "Credential for the Cloudflare transactional email API.",
        SECRET,
    ),
    "CLOUDFLARE_ACCOUNT_ID": ("Canonical Cloudflare account id for both Vectorize and D1.", PLAIN),
    "NOTIFY_FROM": ("From address for notifications sent by the cron Worker.", PLAIN),
    "NOTIFY_UNSUBSCRIBE_BASE": ("Public base URL used to build unsubscribe links.", PLAIN),
    # --- digichat --------------------------------------------------------
    "DIGICHAT_CHROME_SKIN": ("Chrome skin used by digichat-dev.", PLAIN),
    "DIGICHAT_CONFIG_PATH": ("Path to the digichat config document.", PLAIN),
    "DIGICHAT_POSTGRES_PASSWORD": ("digichat-db Postgres password.", SECRET),
    "DIGICHAT_PUBLISH_HOST": ("Host interface digichat's published port binds to.", PLAIN),
    "DIGICHAT_PUBLISH_PORT": (
        "Host port for digichat (3005 by default; the container listens on 3000).",
        PLAIN,
    ),
    "DIGICHAT_EMBED_HOSTS": ("Origins allowed to embed digichat. A closed list.", PLAIN),
    "DIGICHAT_ENABLED_SERVICES": (
        "Backends digichat may call. Deployed workers set `digigraph`; local dev enables four.",
        PLAIN,
    ),
    "DIGICHAT_REQUIRE_ROOT_AUTH": ("`0` allows the anonymous embed path.", PLAIN),
    "DIGICHAT_AUTO_MIGRATE": ("`1` runs digichat migrations at boot.", PLAIN),
    "DIGICHAT_BOOTSTRAP_TENANT_SLUG": ("Tenant created at first boot.", PLAIN),
    "DIGICHAT_DEFAULT_TENANT_SLUG": ("Tenant used when a request carries none.", PLAIN),
    "DIGICHAT_BOOTSTRAP_API_KEY": ("API key minted for the bootstrap tenant.", SECRET),
    "DIGICHAT_DATABASE_URL": (
        "digichat Postgres DSN. Deliberately unset in the DB-less Cloudflare deployment.",
        SECRET,
    ),
    "DIGICHAT_DEV_AUTH": ("Enables the local dev auth bypass.", PLAIN),
    "DIGICHAT_DEV_PASSWORD": ("Password for the local dev auth bypass.", PLAIN),
    "DIGICHAT_MODEL": ("Default model slug for digichat replies.", PLAIN),
    "DIGICHAT_OPENWEBUI_FORMAT": ("Emit OpenWebUI-compatible message envelopes.", PLAIN),
    "DIGICHAT_TRACE_UI": ("Render the trace panel in digichat.", PLAIN),
    "NEXT_PUBLIC_DIGICHAT_TRACE_UI": ("Browser-visible twin of DIGICHAT_TRACE_UI.", PLAIN),
    "DIGI_TENANT_CORPUS_MAP": (
        "Per-tenant digisearch index and digivault prefix. Value copied verbatim from the stack Worker.",
        PLAIN,
    ),
    "DIGICHAT_ENDPOINT_HOST_ALLOWLIST": ("Hosts digichat will proxy to.", PLAIN),
    "DIGICHAT_LEGACY_EMBED_ENABLED": (
        "Legacy anonymous embed. Permanently commented out; not a live var.",
        PLAIN,
    ),
    "DIGICHAT_WEB_SEARCH": ("Enables digichat web search.", PLAIN),
    "NEXT_PUBLIC_DIGICHAT_WEB_SEARCH": ("Browser-visible twin of DIGICHAT_WEB_SEARCH.", PLAIN),
    "DIGICHAT_TRUSTED_PROXIES": ("Proxies whose forwarded headers digichat trusts.", PLAIN),
    "DIGICHAT_MONITOR_TOKENS": ("Tokens for the availability monitors.", SECRET),
    "DIGICHAT_PLAN_PROOF_SECRET": ("Secret backing the plan-proof endpoint.", SECRET),
    "DIGICHAT_DIST_DIR": ("Directory holding the built digichat client.", PLAIN),
    "DIGICHAT_LICENSE_JWT": ("Tenant licence JWT.", SECRET),
    "DIGICHAT_LICENSE_JWT_FILE": ("File path holding the tenant licence JWT.", PLAIN),
    "DIGICHAT_LICENSE_PUBLIC_KEY": ("Public key verifying tenant licences.", PLAIN),
    "DIGICHAT_EMBED_TENANTS": ("Per-tenant embed configuration JSON, including tokens.", SECRET),
    "DIGICHAT_EMBED_TOKEN": ("Shared embed token.", SECRET),
    "DIGICHAT_BFF_TOKEN": ("Server-to-server token for digichat's backend calls.", SECRET),
    "DIGICHAT_LOCAL_AUTH_KEY": ("Local auth key for dev.", SECRET),
    "DIGICHAT_DASHBOARD_SUPABASE_URL": (
        "Deleted after the collapse onto SUPABASE_URL. Do not re-add.",
        PLAIN,
    ),
    "DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY": (
        "Deleted after the collapse onto SUPABASE_ANON_KEY. Do not re-add.",
        SECRET,
    ),
    # --- internal service URLs -------------------------------------------
    "DIGIGRAPH_INTERNAL_URL": ("digigraph base URL as called by digichat.", PLAIN),
    "DIGIQUANT_INTERNAL_URL": ("digiquant base URL as called by digichat.", PLAIN),
    "DIGISEARCH_INTERNAL_URL": ("digisearch base URL as called by digichat.", PLAIN),
    "DIGITRACE_INTERNAL_URL": ("digitrace base URL as called by digichat.", PLAIN),
    "DIGIGRAPH_HOST": ("Host the digigraph dev server binds to.", PLAIN),
    "DIGIGRAPH_PORT": ("Port the digigraph dev server binds to.", PLAIN),
    "DIGIQUANT_HOST": ("Host the digiquant dev server binds to.", PLAIN),
    "DIGIQUANT_PORT": ("Port the digiquant dev server binds to.", PLAIN),
    # --- platform / misc -------------------------------------------------
    "SUPABASE_URL": ("Shared Supabase project URL.", PLAIN),
    "SUPABASE_ANON_KEY": ("Supabase anon key, safe for browser use.", SECRET),
    "GRAFANA_ADMIN_USER": ("Grafana admin user.", PLAIN),
    "GRAFANA_ADMIN_PASSWORD": ("Grafana admin password.", SECRET),
    "DIGI_OTEL_ENDPOINT": ("OTLP endpoint services export spans to.", PLAIN),
    "OTEL_EXPORTER_OTLP_ENDPOINT": ("Standard OTLP exporter endpoint.", PLAIN),
    "DIGI_PROJECT_CONFIG": ("Path to the project config document.", PLAIN),
    "DIGI_ALLOWED_ORIGINS": ("CORS allowlist for the digigraph dev server.", PLAIN),
    "DIGI_ENABLE_DEBUG_ENDPOINTS": ("Exposes debug endpoints.", PLAIN),
    "DIGI_ENABLE_THREAD_API": ("Exposes the thread API.", PLAIN),
    "DIGI_ALLOW_CODE_EXEC": ("Allows code execution. Dev-only; `0` everywhere else.", PLAIN),
    "DIGI_MCP_BIND": ("Bind address for the MCP server.", PLAIN),
    "DIGI_MCP_REQUIRE_AUTH": ("Requires auth on the MCP server.", PLAIN),
    "DIGI_TRUSTED_PROXIES": ("Proxies whose forwarded headers digi services trust.", PLAIN),
    "DIGI_CHECKPOINTER": ("Checkpoint backend for agent graphs.", PLAIN),
    "DIGI_CHECKPOINTER_DATABASE_URL": ("Checkpoint store DSN.", SECRET),
    "DIGISEARCH_INGEST_ROOT": ("Directory digisearch ingests from.", PLAIN),
    "CLICKHOUSE_CLUSTER_ENABLED": (
        "`false` runs single-node ClickHouse without ON CLUSTER.",
        PLAIN,
    ),
    "LANGFUSE_S3_EVENT_UPLOAD_BUCKET": ("R2 bucket receiving Langfuse events.", PLAIN),
    "LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE": ("R2 path-style addressing.", PLAIN),
    "LANGFUSE_S3_EVENT_UPLOAD_PREFIX": ("Key prefix for Langfuse event objects.", PLAIN),
    "LANGFUSE_S3_EVENT_UPLOAD_REGION": ("`auto` is the R2 region convention.", PLAIN),
    "CLICKHOUSE_DB": ("ClickHouse database name.", PLAIN),
    "CLICKHOUSE_USER": ("ClickHouse user.", PLAIN),
    "CLICKHOUSE_PASSWORD": ("ClickHouse password.", SECRET),
    # --- compose literal env (no ${} interpolation) -------------------------
    "AUDIT_LOG_PATH": ("Where the audit log is written.", PLAIN),
    "DIGICLAW_AGENTS_DIR": ("Directory holding digiclaw agent definitions.", PLAIN),
    "DIGICLAW_SCHEDULER_STATE": ("File holding the digiclaw scheduler cursor.", PLAIN),
    "DIGIGRAPH_URL": ("digigraph base URL as set inside compose.", PLAIN),
    "DIGIQUANT_DATA_DIR": ("digiquant data directory inside the container.", PLAIN),
    "Digi_CONFIG_PATH_PLACEHOLDER": ("unused", PLAIN),
    "DIGI_CONFIG_PATH": ("Path to the digi config document.", PLAIN),
    "DIGI_WORKSPACE": ("Workspace root for digiclaw.", PLAIN),
    "EXPORT_OUTPUT_DIR": ("Directory exports are written to.", PLAIN),
    "GF_ANALYTICS_REPORTING_ENABLED": ("Grafana usage reporting toggle.", PLAIN),
    "GF_USERS_ALLOW_SIGN_UP": ("Grafana self sign-up toggle.", PLAIN),
    "NODE_ENV": ("Node runtime mode.", PLAIN),
    "OPENAI_API_BASE": ("OpenAI-compatible base URL, pointing at LiteLLM inside the stack.", PLAIN),
    "PORT": ("Port a service listens on, set literally in compose.", PLAIN),
    "PYTHONUNBUFFERED": ("Unbuffered Python stdout.", PLAIN),
    "ZAMMAD_MCP_ALLOWED_HOSTS": ("Hosts the Zammad MCP will proxy to.", PLAIN),
    "ZAMMAD_MCP_HOST": ("Bind address for the Zammad MCP.", PLAIN),
}


def main() -> int:
    compose = compose_env_names()
    examples = env_example_names()
    literal = compose_literal_env_names()
    worker_vars, worker_bindings = wrangler_inventory()

    var_names: set[str] = set()
    workers_for: dict[str, set[str]] = {}
    values_for: dict[str, dict] = {}
    for worker, variables in worker_vars.items():
        for name, value in variables.items():
            var_names.add(name)
            workers_for.setdefault(name, set()).add(worker)
            values_for.setdefault(name, {}).setdefault(worker, value)

    everything = set(compose) | set(examples) | var_names | literal
    missing = sorted(everything - set(META))
    if missing:
        print("MISSING_DESCRIPTIONS", len(missing))
        for name in missing:
            print("  ", name)
        return 1

    env_rows = []
    for name in sorted(everything):
        description, secret = META[name]
        row: dict = {
            "name": name,
            "description": description,
            "secret": secret,
            "sources": {
                "wrangler_workers": sorted(workers_for.get(name, ())),
                "compose_files": sorted(compose.get(name, ())),
                "env_example_files": sorted(examples.get(name, ())),
                "compose_literal": sorted(name for name in [name] if name in literal),
            },
        }
        if name in values_for:
            row["wrangler_values"] = values_for[name]
        env_rows.append(row)

    document = {
        "version": 1,
        "description": (
            "Self-host stack contract: services, ports, env, secrets and bindings. "
            "Source of truth for config/contract generators and for check_contract.py."
        ),
        "generated_by": "config/contract/bootstrap_contract.py (checked in; edit the YAML, not the script)",
        "notes": [
            "The brief cited ~/local-stack-plan.md sections 0/1/8. That file does not exist; "
            "this contract was derived from the repository itself.",
            "wrangler.toml does not declare secrets. The secrets section is transcribed from the "
            "documented per-worker checklists and is NOT mechanically verified by check_contract.py.",
        ],
        "services": service_rows(),
        "ports": port_rows(),
        "env": env_rows,
        "secrets": secret_rows(),
        "bindings": binding_rows(worker_bindings),
    }

    import yaml  # PyYAML, present in the repo venv

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "# GENERATED ONCE by config/contract/bootstrap_contract.py, then maintained by hand.\n"
        "# This file is the SOURCE OF TRUTH. check_contract.py proves every wrangler var,\n"
        "# every wrangler binding and every compose interpolation maps to an entry here.\n"
        "# Never paste a secret value into this file.\n"
        + yaml.safe_dump(document, sort_keys=False, width=100, allow_unicode=True),
        encoding="utf-8",
    )
    print("WROTE", OUT.relative_to(ROOT), OUT.stat().st_size, "bytes")
    print("services", len(document["services"]), "ports", len(document["ports"]))
    print(
        "env",
        len(env_rows),
        "secrets",
        len(document["secrets"]),
        "bindings",
        len(document["bindings"]),
    )
    print("worker_vars_total", sum(len(v) for v in worker_vars.values()), "unique", len(var_names))
    return 0


def service_rows() -> list[dict]:
    import yaml as _yaml

    raw = _yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    rows = []
    for name, spec in (raw.get("services") or {}).items():
        ports = spec.get("ports") or []
        rows.append(
            {
                "name": name,
                "compose_file": "docker-compose.yml",
                "image": spec.get("image"),
                "build_context": spec.get("build"),
                "ports": [str(p) for p in ports],
                "profiles": spec.get("profiles") or [],
            }
        )
    local = _yaml.safe_load((ROOT / "apps/digitrace-langfuse/docker-compose.local.yml").read_text())
    for name, spec in (local.get("services") or {}).items():
        rows.append(
            {
                "name": name,
                "compose_file": "apps/digitrace-langfuse/docker-compose.local.yml",
                "image": spec.get("image"),
                "build_context": spec.get("build"),
                "ports": [str(p) for p in (spec.get("ports") or [])],
                "profiles": spec.get("profiles") or [],
                "note": "local dev only",
            }
        )
    return rows


def port_rows() -> list[dict]:
    return [
        {
            "name": "digigraph",
            "container_port": 8000,
            "host_port": 8000,
            "note": "public route graph.digithings.ai",
        },
        {"name": "digiquant", "container_port": 8001, "host_port": 8001},
        {
            "name": "digisearch",
            "container_port": 8002,
            "host_port": 8002,
            "note": "public route search.digithings.ai; binds 0.0.0.0 in-container so the Worker can proxy (#4071)",
        },
        {"name": "digitrace", "container_port": 8003, "host_port": 8003},
        {"name": "digivault", "container_port": 8004, "host_port": 8004},
        {
            "name": "digikey",
            "container_port": 8005,
            "host_port": 8005,
            "note": "public route key.digithings.ai",
        },
        {"name": "litellm", "container_port": 4000, "host_port": 4000},
        {
            "name": "ollama",
            "container_port": 11434,
            "host_port": 11435,
            "note": "host port is remapped",
        },
        {
            "name": "digichat",
            "container_port": 3000,
            "host_port": 3005,
            "note": "host port is DIGICHAT_PUBLISH_PORT, default 3005",
        },
        {
            "name": "digichat-db",
            "container_port": 5432,
            "host_port": 5433,
            "note": "host port is remapped",
        },
        {"name": "digisearch-mcp", "container_port": 8765, "host_port": 8765},
        {"name": "digivault-mcp", "container_port": 8769, "host_port": 8769},
        {"name": "zammad-mcp", "container_port": 8770, "host_port": 8770},
        {"name": "searxng", "container_port": 8080, "host_port": 8080},
        {"name": "omniroute", "container_port": 20128, "host_port": 20128},
        {"name": "prometheus", "container_port": 9090, "host_port": 9090},
        {
            "name": "grafana",
            "container_port": 3000,
            "host_port": 3001,
            "note": "host port is remapped",
        },
        {
            "name": "otel-collector",
            "container_port": 4317,
            "host_port": 4317,
            "note": "gRPC 4317 and HTTP 4318",
        },
        {
            "name": "digiquant-mcp-container",
            "container_port": 8767,
            "host_port": None,
            "note": "FastMCP inside the stack Worker, not published",
        },
    ]


def secret_rows() -> list[dict]:
    return [
        {
            "name": "DIGIKEY_DATABASE_URL",
            "worker": "digithings-stack",
            "required": True,
            "note": "a var fallback would lose every issued key and the revocation blocklist on the next instance replace (#4080)",
        },
        {
            "name": "DIGIKEY_PRIVATE_KEY_PEM",
            "worker": "digithings-stack",
            "required": True,
            "note": "stable RS256 key; no ephemeral keys in production",
        },
        {
            "name": "DIGIKEY_BFF_TOKEN",
            "worker": "digithings-stack, digithings-digichat",
            "required": True,
        },
        {"name": "DIGIKEY_ADMIN_TOKEN", "worker": "digithings-stack", "required": False},
        {"name": "LITELLM_PROXY_API_KEY", "worker": "digithings-stack", "required": True},
        {"name": "GROQ_API_KEY", "worker": "digithings-stack", "required": False},
        {"name": "OPENROUTER_API_KEY", "worker": "digithings-stack", "required": False},
        {"name": "OPENAI_API_KEY", "worker": "digithings-stack", "required": False},
        {"name": "CHEAPERINFERENCE_API_KEY", "worker": "digithings-stack", "required": False},
        {
            "name": "ZAMMAD_API_TOKEN",
            "worker": "digithings-stack",
            "required": False,
            "note": "read-only ticketing MCP",
        },
        {
            "name": "GLOOMBERB_SESSION_COOKIE",
            "worker": "digithings-stack",
            "required": False,
            "note": "not a shared digithings credential; owner is the deployer",
        },
        {"name": "R2_ACCOUNT_ID", "worker": "digithings-stack, digiquant-runner", "required": True},
        {"name": "R2_BUCKET", "worker": "digithings-stack, digiquant-runner", "required": True},
        {
            "name": "R2_ACCESS_KEY_ID",
            "worker": "digithings-stack, digiquant-runner",
            "required": True,
        },
        {
            "name": "R2_SECRET_ACCESS_KEY",
            "worker": "digithings-stack, digiquant-runner",
            "required": True,
        },
        {
            "name": "CLOUDFLARE_ACCOUNT_ID",
            "worker": "digithings-stack, digiquant-runner",
            "required": True,
        },
        {
            "name": "CLOUDFLARE_API_TOKEN",
            "worker": "digithings-stack, digiquant-runner",
            "required": True,
            "note": "same account as CLOUDFLARE_ACCOUNT_ID; also wrangler's own auth var, so unset it before any wrangler secret put",
        },
        {
            "name": "D1_DATABASE_MAP",
            "worker": "digithings-stack",
            "required": True,
            "note": "tenant -> D1 id JSON",
        },
        {
            "name": "SUPABASE_SERVICE_ROLE_KEY",
            "worker": "dashboard-api",
            "required": True,
            "note": "worker secret; never in the static bundle",
        },
        {
            "name": "RUNNER_AUTH_TOKEN",
            "worker": "digiquant-runner, digithings-cron",
            "required": True,
        },
        {"name": "CORE_POSTGRES_URI", "worker": "digiquant-runner", "required": True},
        {"name": "CORE_SUPABASE_URL", "worker": "digiquant-runner", "required": True},
        {"name": "CORE_SUPABASE_SERVICE_KEY", "worker": "digiquant-runner", "required": True},
        {"name": "CLOUDFLARE_EMAIL_API_TOKEN", "worker": "digiquant-runner", "required": False},
        {"name": "NOTIFY_FROM", "worker": "digiquant-runner", "required": False},
        {
            "name": "GH_DISPATCH_TOKEN",
            "worker": "digithings-cron",
            "required": True,
            "note": "Actions write + Issues read/write; no Contents grant, so use REST not the GraphQL gh CLI",
        },
        {
            "name": "CRON_KICK_SECRET",
            "worker": "digithings-cron",
            "required": False,
            "note": "enables POST /kick and GET /runs/:id",
        },
        {
            "name": "AUTH_SECRET",
            "worker": "digithings-digichat, digithings-stack",
            "required": True,
        },
        {
            "name": "DIGICHAT_EMBED_TENANTS",
            "worker": "digithings-digichat, digithings-stack",
            "required": True,
        },
        {
            "name": "DIGIGRAPH_INTERNAL_URL",
            "worker": "digithings-digichat, digithings-stack",
            "required": True,
        },
        {
            "name": "DIGIKEY_URL",
            "worker": "digithings-digichat, digithings-stack",
            "required": True,
        },
        {
            "name": "DIGICHAT_PLAN_PROOF_SECRET",
            "worker": "digithings-digichat, digithings-stack",
            "required": True,
        },
        {"name": "DIGICHAT_MONITOR_TOKENS", "worker": "digithings-digichat", "required": False},
        {"name": "DATABASE_URL", "worker": "digitrace-langfuse", "required": True},
        {"name": "NEXTAUTH_SECRET", "worker": "digitrace-langfuse", "required": True},
        {"name": "SALT", "worker": "digitrace-langfuse", "required": True},
        {
            "name": "ENCRYPTION_KEY",
            "worker": "digitrace-langfuse",
            "required": True,
            "note": "openssl rand -hex 32",
        },
        {"name": "NEXTAUTH_URL", "worker": "digitrace-langfuse", "required": True},
        {"name": "CLICKHOUSE_URL", "worker": "digitrace-langfuse", "required": True},
        {"name": "CLICKHOUSE_MIGRATION_URL", "worker": "digitrace-langfuse", "required": True},
        {"name": "CLICKHOUSE_USER", "worker": "digitrace-langfuse", "required": True},
        {"name": "CLICKHOUSE_PASSWORD", "worker": "digitrace-langfuse", "required": True},
        {
            "name": "REDIS_CONNECTION_STRING",
            "worker": "digitrace-langfuse",
            "required": False,
            "note": "preferred over REDIS_HOST/PORT/AUTH",
        },
        {
            "name": "LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID",
            "worker": "digitrace-langfuse",
            "required": True,
        },
        {
            "name": "LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY",
            "worker": "digitrace-langfuse",
            "required": True,
        },
    ]


def binding_rows(worker_bindings: dict) -> list[dict]:
    rows = []
    for worker, items in sorted(worker_bindings.items()):
        for item in items:
            rows.append({"worker": worker, **item})
    return rows


if __name__ == "__main__":
    sys.exit(main())
