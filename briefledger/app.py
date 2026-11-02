"""FastAPI application: bounded JSON API and an inert, same-origin web interface."""

import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.types import ASGIApp, Receive, Scope, Send

from .errors import StoreError
from .store import SESSION_SECONDS, TOKEN_PATTERN, BrowserCollection, Registry

ROOT = Path(__file__).parent
COOKIE = "briefledger_session"
MAX_BODY = 256 * 1024


class Upload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    filename: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=131072)


class Reset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: StrictBool


class SecurityMiddleware:
    """Bound raw bodies before framework parsing and apply security headers to every response."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def secure_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                        ),
                        (b"cache-control", b"no-store"),
                    ]
                )
                message["headers"] = headers
            await send(message)

        downstream_receive = receive
        if scope["method"] in ("POST", "PUT", "PATCH", "DELETE"):
            headers = dict(scope["headers"])
            length = headers.get(b"content-length")
            if length and (len(length) > 12 or not length.isdigit() or int(length) > MAX_BODY):
                await JSONResponse({"error": "Request body must be at most 256 KiB."}, 413)(
                    scope, receive, secure_send
                )
                return
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > MAX_BODY:
                    await JSONResponse({"error": "Request body must be at most 256 KiB."}, 413)(
                        scope, receive, secure_send
                    )
                    return
                if not message.get("more_body", False):
                    break
            replayed = False

            async def replay():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            downstream_receive = replay
        await self.app(scope, downstream_receive, secure_send)


def create_app(data_dir: Path | str | None = None, cookie_secure: bool | None = None) -> FastAPI:
    directory = Path(data_dir or os.environ.get("BRIEFLEDGER_DATA_DIR", "./data"))
    secure_cookie = (
        cookie_secure
        if cookie_secure is not None
        else os.getenv("BRIEFLEDGER_COOKIE_SECURE", "true").lower() != "false"
    )
    public_origin = os.getenv("BRIEFLEDGER_ORIGIN") or os.getenv("RENDER_EXTERNAL_URL")
    if public_origin:
        parsed = urlsplit(public_origin)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError("BRIEFLEDGER_ORIGIN must be a bare HTTP(S) origin.")
        public_origin = f"{parsed.scheme}://{parsed.netloc}"
    registry = Registry(directory)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        registry.initialize()
        yield

    app = FastAPI(
        title="BriefLedger",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(SecurityMiddleware)
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.exception_handler(StoreError)
    async def handle_store_error(_: Request, error: StoreError):
        return JSONResponse({"error": str(error)}, error.status)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, __: RequestValidationError):
        # Never echo source text, cookie values, raw request bodies or framework internals.
        return JSONResponse({"error": "Check the request fields, filename, and text limits."}, 400)

    @app.exception_handler(sqlite3.Error)
    async def handle_database_error(_: Request, __: sqlite3.Error):
        return JSONResponse(
            {"error": "Collection storage is temporarily unavailable. Try again shortly."}, 503
        )

    def collection(request: Request) -> BrowserCollection:
        current = registry.lookup(request.cookies.get(COOKIE))
        if current is None:
            raise StoreError("Open the workbench to start or renew your private collection.", 401)
        if request.method in ("POST", "DELETE", "PUT", "PATCH"):
            expected = public_origin or f"{request.url.scheme}://{request.url.netloc}"
            if (
                request.headers.get("origin") != expected
                or request.headers.get("sec-fetch-site") == "cross-site"
            ):
                raise StoreError("Submit changes from this workbench.", 403)
            csrf = request.headers.get("x-csrf-token", "")
            if not TOKEN_PATTERN.fullmatch(csrf) or not secrets.compare_digest(csrf, current.csrf):
                raise StoreError("Refresh the workbench before submitting changes.", 403)
            if (
                request.headers.get("content-type", "").split(";")[0].strip().lower()
                != "application/json"
            ):
                raise StoreError("Content-Type must be application/json.", 415)
        return current

    Collection = Annotated[BrowserCollection, Depends(collection)]

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse((ROOT / "templates" / "index.html").read_text())

    @app.get("/healthz")
    def health():
        # Deployment readiness checks SQLite/FTS5 availability without creating a browser collection.
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE VIRTUAL TABLE readiness USING fts5(body)")
        return {"status": "ok", "service": "briefledger"}

    @app.get("/api/session")
    def browser_session(request: Request):
        current = registry.lookup(request.cookies.get(COOKIE))
        is_new = current is None
        if current is None:
            current = registry.create()
        ephemeral = os.getenv("BRIEFLEDGER_EPHEMERAL", "false").lower() == "true"
        payload = {
            "csrfToken": current.csrf,
            "expiresAt": datetime.fromtimestamp(current.expires_at, UTC).isoformat(),
            "documents": current.store.list_documents(),
            "stats": current.store.stats(),
            "storage": "ephemeral" if ephemeral else "local",
            "storageNotice": (
                "Collections may reset when this service restarts or is redeployed. "
                "Use synthetic or sample text only."
            )
            if ephemeral
            else None,
        }
        response = JSONResponse(payload)
        if is_new:
            response.set_cookie(
                COOKIE,
                current.token,
                max_age=SESSION_SECONDS,
                httponly=True,
                secure=secure_cookie,
                samesite="lax",
                path="/",
            )
        return response

    @app.get("/api/documents")
    def documents(current: Collection):
        return {"documents": current.store.list_documents(), "stats": current.store.stats()}

    @app.post("/api/documents", status_code=201)
    def upload(payload: Upload, current: Collection):
        document = current.store.add(payload.filename, payload.content)
        return {"document": document, "stats": current.store.stats()}

    @app.get("/api/documents/{document_id}")
    def document(document_id: str, current: Collection):
        return current.store.document(document_id)

    @app.delete("/api/documents/{document_id}")
    def delete(document_id: str, current: Collection):
        current.store.delete(document_id)
        return {"deleted": True, "stats": current.store.stats()}

    @app.post("/api/reset")
    def reset(payload: Reset, current: Collection):
        if not payload.confirm:
            raise StoreError(
                "Confirm that you want to replace this collection with sample sources."
            )
        current.store.reset_samples()
        return {"documents": current.store.list_documents(), "stats": current.store.stats()}

    @app.get("/api/search")
    def search(
        current: Collection,
        q: str = Query(min_length=1, max_length=160),
        document_id: str | None = Query(default=None, alias="documentId"),
    ):
        start = time.perf_counter()
        result = current.store.search(q, document_id)
        result["elapsedMs"] = round((time.perf_counter() - start) * 1000, 2)
        return result

    return app


app = create_app()
