# digikey

Central control plane for ecosystem API keys, scoped capabilities, and JWT exchange. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Local run

```bash
export DIGIKEY_DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/digikey
export DIGIKEY_ADMIN_TOKEN=$(openssl rand -hex 16)
uvicorn digikey.server:app --host 127.0.0.1 --port 8005
```

SQLite (tests / quick dev): `DIGIKEY_DATABASE_URL=sqlite:///./digikey.db`

## CLI

```bash
python -m digikey.cli issue-key --tenant default --label dev --scopes '*' --kind dev_global
```

`issue-key` without `--scopes` grants `digigraph:chat,digisearch:query` only
(`DEFAULT_ISSUE_KEY_SCOPES` in `cli.py`). It used to grant `*`, and a `*` key
exchanged at `/v1/oauth/token` opened every MCP edge server (#6648). Name the
scopes a key needs, e.g. `--scopes mcp:digivault` for read-only vault MCP access;
`*` must be passed explicitly, and the MCP edge refuses a bare `*` from any
tenant other than the house. A `dev_global` key with no `--scopes` still gets `*`.
