# Prune onboard vault orphans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make changed docs_onboard segment structures converge in local digivault and Supabase.

**Architecture:** The writer will provide its authoritative child-name set to a narrow
parent/subdirectory-scoped pruning operation after successful upserts. The Supabase sync will
upsert current rows, then remove exact stale paths under the supplied vault prefix using a
guarded shared connector method.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, Supabase Python client, pytest, ruff.

**Spec:** `openspec/changes/prune-onboard-vault-orphans/`

## Global Constraints

- Pydantic v2 models everywhere; no raw core result dicts.
- All local write paths use `Vault._safe_path`; store-backed vaults remain read-only.
- HTTP pruning requires `digivault:write` and is not an MCP/orchestrator capability.
- Supabase deletion must be filtered, exact-set scoped, and audited without note contents.
- Never prune an empty source vault or a confidential `projects/` path.

---

### Task 1: digivault child pruning

**Files:**
- Modify: `tests/dv/test_vault.py`
- Modify: `digivault/src/digivault/vault.py`

**Interfaces:**
- Produces: `Vault.prune_children(parent_doc: str, keep_names: set[str], subdir: str) -> list[str]`

- [ ] **Step 1: Write failing tests**
```python
deleted = vault.prune_children("guide", {"guide__fresh"}, "clients/acme")
assert deleted == ["guide__stale"]
assert vault.get_note("guide__stale") is None
assert vault.get_note("other__stale") is not None
```
- [ ] **Step 2: Verify failure**
Run: `pytest tests/dv/test_vault.py -k prune_children -v`
Expected: failure because `prune_children` does not exist.
- [ ] **Step 3: Implement the minimal scoped prune**
Validate the parent name, all keep names, and subdirectory. Select only indexed child notes whose
name prefix, `parent_doc` frontmatter, and normalized relative path match; unlink them through
safe paths and call `reindex()` once only when candidates exist.
- [ ] **Step 4: Verify green**
Run: `pytest tests/dv/test_vault.py -k prune_children -v`
Expected: PASS.

### Task 2: digivault HTTP and docs_onboard integration

**Files:**
- Modify: `tests/dv/test_server.py`
- Modify: `digivault/src/digivault/server.py`
- Modify: `tests/scripts/docs_onboard/test_write_vault_notes.py`
- Modify: `scripts/docs_onboard/write_vault_notes.py`

**Interfaces:**
- Consumes: `Vault.prune_children(...) -> list[str]`
- Produces: `NoteWriter.prune_children(...) -> list[str]`

- [ ] **Step 1: Write failing endpoint/writer tests**
```python
writer.prune_children(parent_doc=slug, keep_names={f"{slug}__new"}, subdir="clients/acme")
assert vault.get_note(f"{slug}__old") is None
```
- [ ] **Step 2: Verify failure**
Run: `pytest tests/dv/test_server.py tests/scripts/docs_onboard/test_write_vault_notes.py -k prune -v`
Expected: failure because the route and writer method are absent.
- [ ] **Step 3: Implement strict write-scoped endpoint and adapters**
Use Pydantic request/response models; route via normal write policy. Add a JSON POST client method
and call it after current children and hub upserts.
- [ ] **Step 4: Verify green**
Run: `pytest tests/dv/test_server.py tests/scripts/docs_onboard/test_write_vault_notes.py -k prune -v`
Expected: PASS.

### Task 3: guarded Supabase prune

**Files:**
- Modify: `tests/db/connectors/test_supabase_connector.py`
- Modify: `digibase/src/digibase/connectors/supabase.py`
- Modify: `tests/scripts/test_sync_onboard_vault.py`
- Modify: `scripts/sync_onboard_vault.py`

**Interfaces:**
- Produces: `SupabaseConnector.delete(table: str, *, eq: dict[str, Any] | None, in_: dict[str, list[Any] | tuple[Any, ...]] | None) -> SupabaseWriteResult`

- [ ] **Step 1: Write failing connector/sync tests**
```python
result = connector.delete("architecture_notes", in_={"vault_path": ["clients/acme/stale"]})
assert result.success and result.rows == 1
```
- [ ] **Step 2: Verify failure**
Run: `pytest tests/db/connectors/test_supabase_connector.py tests/scripts/test_sync_onboard_vault.py -k 'delete or prune' -v`
Expected: failure because filtered deletion and sync pruning are absent.
- [ ] **Step 3: Implement exact-set prune**
Require at least one filter in the connector; apply all filters to PostgREST delete; return a
typed result. In sync, upsert first, read only candidate paths under the vault prefix, and delete
the computed stale set. Return failure if prune fails.
- [ ] **Step 4: Verify green**
Run: `pytest tests/db/connectors/test_supabase_connector.py tests/scripts/test_sync_onboard_vault.py -k 'delete or prune' -v`
Expected: PASS.

### Task 4: documentation and verification

**Files:**
- Modify: `digivault/ARCHITECTURE.md`
- Modify: `digibase/ARCHITECTURE.md`

- [ ] **Step 1: Document interfaces and safety boundaries**
- [ ] **Step 2: Run focused validation**
Run: `pytest tests/dv tests/scripts/docs_onboard/test_write_vault_notes.py tests/scripts/test_sync_onboard_vault.py tests/db/connectors/test_supabase_connector.py -m unit -v`
Expected: PASS.
- [ ] **Step 3: Run static checks**
Run: `ruff check digivault/src/digivault digibase/src/digibase scripts/docs_onboard/write_vault_notes.py scripts/sync_onboard_vault.py tests/dv tests/scripts/docs_onboard/test_write_vault_notes.py tests/scripts/test_sync_onboard_vault.py tests/db/connectors/test_supabase_connector.py && ruff format --check digivault/src/digivault digibase/src/digibase scripts/docs_onboard/write_vault_notes.py scripts/sync_onboard_vault.py tests/dv tests/scripts/docs_onboard/test_write_vault_notes.py tests/scripts/test_sync_onboard_vault.py tests/db/connectors/test_supabase_connector.py`
Expected: PASS.
