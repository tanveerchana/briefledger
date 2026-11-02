# BriefLedger Implementation Plan

> For agentic workers: execute the already-authorized task natively. Test each behavior before implementing it.

**Goal:** Deliver a complete Python evidence search workbench with private document collections.

**Architecture:** FastAPI routes use a registry for anonymous browser capabilities and separate SQLite FTS5 databases for each collection. Static HTML/CSS/JS presents actual evidence and line-addressable source text.

**Tech stack:** Python 3.12+, pinned FastAPI/Pydantic/Uvicorn, built-in sqlite3/FTS5, pytest/HTTPX and Ruff.

**Spec:** ../specs/2026-11-01-briefledger-design.md

## Global constraints

- Keep all state local; no external credentials or paid AI.
- Enforce 128 KiB/document, 30 documents/collection, 2 MiB/collection and 256 KiB request bodies.
- Preserve visible source references, isolation and explicit no-match behavior.
- Do not publish or create external databases; parent handles deployment.

## Review focus

- SQL/FTS metacharacters must never become search operators.
- Another browser must not read, rank against, delete or reset a different collection.
- Long lines, Unicode and newline normalization must keep valid source locations.
- HTML in source content must remain inert plain text.
- Storage limits, expiry and partial writes must fail clearly and atomically.

### Task 1: Retrieval and collection storage

Files: briefledger/search.py, briefledger/store.py, briefledger/samples.py, tests/test_store.py.

- [x] Write and run failing tests for source chunks, search ranking/no-match, isolation, deletion, reset, quotas and malformed text.
- [x] Implement chunk_text(text), safe_query(query), CollectionStore(path) and Registry(directory) with transactions and bounded inputs.
- [x] Run pytest tests/test_store.py; require all assertions pass.

### Task 2: HTTP and browser protection

Files: briefledger/app.py, tests/test_api.py.

- [x] Write and run failing tests for session cookies, CSRF/origin checks, uploads, cross-collection IDs, body bounds and safe errors.
- [x] Implement create_app(data_dir, cookie_secure) and JSON API with strict models, security headers and pre-parse request limits.
- [x] Run full pytest; require all assertions pass.

### Task 3: Workbench UI and packaging

Files: briefledger/templates/index.html, briefledger/static/{app.js,style.css}, Dockerfile, README.md, .github/workflows/ci.yml.

- [x] Build responsive collection/search/evidence/source/upload flows against the real API.
- [x] Verify all tests, Ruff and a real HTTP smoke run; inspect desktop/mobile screenshots when browser tooling permits.
- [x] Document setup, architecture, retrieval semantics, privacy and persistence limits; provide pinned dependencies and CI.

## Verification record

43 tests pass on Python 3.12.14; Ruff checks and formatting, JavaScript syntax, static-asset formatting, dependency consistency and Python compilation pass. A real Uvicorn HTTP smoke covers health, cookie session, upload, ranked evidence, source reading, deletion, explicit no-match and sample reset. Docker configuration is provided but no Docker build is claimed. Browser visual verification remains with the parent deployment workflow: the CUA remote browser cannot reach this executor localhost. No service was published or external database created by this task.
