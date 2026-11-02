# BriefLedger

**Find the passage. Keep the source.**

BriefLedger is a Python document search workbench that returns actual evidence from a private browser collection. Upload a text or Markdown file, search a few terms, inspect highlighted excerpts, and open the original source at its line range. It runs with **FastAPI, SQLite FTS5, and plain HTML/CSS/JavaScript**. There is no React build, external database, paid API, embedding service, or LLM.

> This is lexical retrieval, not generated AI answers. If the text does not match, BriefLedger says **“No supporting passage found.”** It never invents an answer or a citation.

[Live demo](https://briefledger.onrender.com/) · [CI checks](https://github.com/tanveerchana/briefledger/actions) · [Hosted verification](docs/hosted-verification.md)

The free demo uses temporary storage and can take time to wake after idle spin-down. Use synthetic text only.

## Run locally

Requires Python 3.12+ with SQLite FTS5 (the official Python Linux image and normal CPython packages include it).

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
BRIEFLEDGER_COOKIE_SECURE=false python -m uvicorn briefledger.app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. The first visit creates a private collection with four clearly labelled synthetic sources. Try **rollback**, **access reviews**, or **retention**, then upload a `.txt` or `.md` file of your own. Use the Sources view or a result’s **View source** action to inspect the full line-numbered text. `/` focuses search; Escape closes a dialog.

`BRIEFLEDGER_COOKIE_SECURE=false` is an explicit local HTTP development setting. Production defaults to Secure cookies. Environment files are not loaded implicitly; export the values you need or let your host set them.

## Check it

```bash
pytest -q
ruff check .
ruff format --check .
python -m compileall -q briefledger
```

The suite uses real temporary SQLite databases and the ASGI application. It covers chunk/source alignment, Unicode and long lines, BM25 ranking, literal query syntax, no-match behavior, complete index deletion, private collections, quotas, duplicate documents, session expiry/capacity, restart persistence, protected cookies, CSRF/origin checks, malformed data, body limits, inert markup, and reset confirmation. CI runs the checks on Python 3.12 and 3.13; Python 3.12 is the locally verified runtime.

## Docker

```bash
docker build -t briefledger .
docker run --rm -p 8000:8000 -e BRIEFLEDGER_COOKIE_SECURE=false -v briefledger-data:/data briefledger
```

The container runs as a non-root user, honors `PORT`, and has a `/healthz` health check. Use HTTPS and the default Secure cookie setting for a public deployment. A persistent volume at `/data` is needed to preserve collections across container replacement. Make mounted storage writable by UID/GID `10001`.

For native Python hosting, use `pip install -r requirements.lock` as the build command and `python -m briefledger` as the start command. `/healthz` checks that SQLite FTS5 is available without creating a collection.

| Environment variable        | Default                      | Purpose                                                                                                                                        |
| --------------------------- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `PORT`                      | `8000`                       | Listening port, passed explicitly to Uvicorn.                                                                                                  |
| `HOST`                      | `0.0.0.0`                    | Bind address for the module entry point.                                                                                                       |
| `BRIEFLEDGER_DATA_DIR`      | `./data` (`/data` in Docker) | Registry and private collection databases.                                                                                                     |
| `BRIEFLEDGER_COOKIE_SECURE` | `true`                       | Secure browser cookie; set false only for local HTTP.                                                                                          |
| `BRIEFLEDGER_ORIGIN`        | Derived from the request     | Bare public origin for write-origin validation behind a reverse proxy. `RENDER_EXTERNAL_URL`, when present, is also recognized.                |
| `BRIEFLEDGER_EPHEMERAL`     | `false`                      | Show an explicit restart-loss disclosure in the interface. Set true on hosting without persistent storage.                                     |
| `FORWARDED_ALLOW_IPS`       | `127.0.0.1`                  | Trusted reverse proxies for Uvicorn. Set only to the actual proxy network; no wildcard trust is required when the public origin is configured. |

A free host with ephemeral storage can run the workbench, but uploaded sources may disappear on restart, redeploy, or service recycling. Set `BRIEFLEDGER_EPHEMERAL=true` to display a prominent temporary-storage notice above both Search and Sources, including on mobile. The notice explicitly permits synthetic/sample text only. This flag is a disclosure; it does not remove or weaken local SQLite persistence. No persistent-storage or hosting plan is purchased by this repository.

For a free ephemeral Render Python service:

- Build command: `pip install -r requirements.lock`
- Start command: `python -m briefledger`
- Health check: `/healthz`
- Environment: `PYTHON_VERSION=3.12.14`, `BRIEFLEDGER_DATA_DIR=/tmp/briefledger`, `BRIEFLEDGER_COOKIE_SECURE=true`, `BRIEFLEDGER_EPHEMERAL=true`
- Render supplies `PORT` and `RENDER_EXTERNAL_URL`; the runner honors the port and the application uses the external URL for same-origin checks. No secret environment variables or external databases are needed.

Local installations keep their SQLite data across application restarts when the configured data directory is retained. The normal local mode does not show the hosted ephemeral-storage notice.

## How retrieval works

1. **Keep the text.** The server validates UTF-8 content and normalizes CRLF/CR newlines to LF. Markdown and HTML remain plain text.
2. **Chunk with provenance.** Passages contain at most 1,400 characters with roughly 180 characters of overlap. Each stores its source document ID, exact character slice, heading, and line range.
3. **Match literal terms.** A query becomes up to twelve safely quoted words joined with `AND`. User-supplied SQL, quotes, `OR`, `NEAR`, and wildcard punctuation cannot become executable query operators. English Porter stemming and Unicode tokenization are enabled. This is word matching, not semantic understanding or Boolean/phrase-query syntax.
4. **Rank evidence.** SQLite FTS5 BM25 ranks matching passages; lower internal values rank first. The UI shows rank order, not fabricated confidence percentages. At most 24 passages are returned, with a visible truncation note.
5. **Inspect the source.** Excerpts come directly from FTS5 `snippet()`. Match flags are rendered through DOM text nodes, never interpreted as HTML. The source reader highlights the retrieved line range and pages large files to keep the interface responsive.

Overlapping passages can produce related results from the same source. A no-match outcome means no passage contains all searchable terms; it is not a claim that the underlying real-world fact is false. Search cannot answer questions whose evidence was never uploaded.

## Architecture and privacy

| File                                               | Responsibility                                                                                                    |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `briefledger/app.py`                               | FastAPI routes, strict request models, response protections, capability/CSRF checks, bounded ASGI request bodies. |
| `briefledger/store.py`                             | Collection registry, quotas, transactionally consistent source/index storage, expiry and private database files.  |
| `briefledger/search.py`                            | Source-preserving chunks, literal FTS syntax, safe snippet segments.                                              |
| `briefledger/samples.py`                           | Four fictional, reproducible demonstration sources.                                                               |
| `briefledger/templates/` and `briefledger/static/` | Same-origin UI without a frontend build chain or third-party scripts.                                             |

The browser receives a random 256-bit opaque session cookie. It is host-only, HttpOnly, SameSite=Lax and Secure by default. The registry stores only its SHA-256 hash, alongside a separate CSRF token and fixed seven-day expiry. Every API lookup resolves the current browser collection; document identifiers never select a different collection.

Each collection has a **separate SQLite database and separate FTS index**. Other visitors’ documents cannot enter either results or BM25 corpus statistics. This is deliberately stronger than applying a tenant filter to a global search index.

Writes require an exact same-origin `Origin`, an unguessable collection CSRF token, and JSON. Cross-site fetches are rejected; there is no permissive CORS. Content Security Policy restricts assets and requests to this origin, forbids framing, and disables document markup execution. Requests, passwords, source text and browser capabilities are not logged by the application; the module runner disables access logs to avoid logging search queries. Configure host/proxy logs appropriately too.

This is anonymous capability access, **not account authentication**. Anyone possessing the browser cookie can access that collection. There is no email, sharing, account recovery, encryption-at-rest claim, or multi-user authorization system. Clearing cookies loses access. Collections become inaccessible after seven days; expired files are lazily removed when the next collection is created. Treat a public instance as a portfolio demo and upload test material rather than sensitive information.

## Explicit limits

| Resource              | Bound                                                             |
| --------------------- | ----------------------------------------------------------------- |
| Source types          | UTF-8 `.txt` and `.md`; no PDF/OCR or remote URLs.                |
| One source            | 128 KiB before normalization.                                     |
| One collection        | 30 sources and 2 MiB of source text, including samples.           |
| Write request body    | 256 KiB, enforced before JSON parsing, including streamed bodies. |
| Search                | 160 characters, 1–12 searchable terms, top 24 matching passages.  |
| Anonymous collections | 500 active collections per installation; seven-day fixed expiry.  |
| Source viewer         | At most 220 rendered lines per page.                              |

SQLite index/WAL files consume additional disk beyond the source-text quota. This is a bounded single-service workbench, not distributed storage or an unrestricted public upload service. Use one service instance with local storage; replicas do not share browser collections. A production public service would also need edge rate controls, operational disk monitoring/backups, and an account/retention policy appropriate to its data.

## Dependency notes and official references

Direct runtime dependencies and their tested transitive closure are pinned in `requirements.lock`; development tooling is pinned in `requirements-dev.lock`. These locks were generated and tested on Python 3.12/Linux. The Docker base tracks Python 3.12 security patches; pin an image digest in a release pipeline if fully immutable images are required.

Current official documentation was checked during implementation: [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/) (0.162.0), [Starlette TestClient](https://starlette.dev/testclient/) (current `httpx2` transport), [Uvicorn settings](https://uvicorn.dev/settings/), and [SQLite FTS5](https://www.sqlite.org/fts5.html) (`bm25`, `snippet`, quoted queries). The tested runtime pins are FastAPI 0.162.0, Pydantic 2.14.2, Starlette 1.10.0 and Uvicorn 0.54.0.

MIT licensed. All bundled sample documents are fictional and included with the project.
