# DigiKey

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
