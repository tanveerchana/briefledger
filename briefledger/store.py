"""Private SQLite databases and an opaque browser-capability registry."""

import hashlib
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .errors import StoreError
from .samples import SAMPLES
from .search import chunk_text, safe_query, snippet_segments

MAX_DOCUMENT_BYTES = 128 * 1024
MAX_COLLECTION_BYTES = 2 * 1024 * 1024
SESSION_SECONDS = 7 * 24 * 60 * 60
TOKEN_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def normalize_upload(filename: str, content: str) -> tuple[str, str]:
    if (
        not isinstance(filename, str)
        or not 1 <= len(filename) <= 120
        or "/" in filename
        or "\\" in filename
        or not filename.lower().endswith((".txt", ".md"))
        or re.search(r"[\x00-\x1f\x7f]", filename)
    ):
        raise StoreError("Choose a .txt or .md filename with no path, up to 120 characters.")
    try:
        filename.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise StoreError("The filename must contain valid UTF-8 text.") from exc
    if not isinstance(content, str) or not content.strip():
        raise StoreError("The source must contain readable text.")
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", content):
        raise StoreError("This source contains binary or unsupported control characters.")
    try:
        size = len(content.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise StoreError("The source must contain valid UTF-8 text.") from exc
    if size > MAX_DOCUMENT_BYTES:
        raise StoreError("Each source must be at most 128 KiB.")
    content = content.replace("\r\n", "\n").replace("\r", "\n").removeprefix("\ufeff")
    if not content.strip():
        raise StoreError("The source must contain readable text.")
    return filename, content


class CollectionStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL, title TEXT NOT NULL,
                    content TEXT NOT NULL, digest TEXT NOT NULL UNIQUE,
                    bytes INTEGER NOT NULL, sample INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY, document_id TEXT NOT NULL
                        REFERENCES documents(id) ON DELETE CASCADE,
                    body TEXT NOT NULL, heading TEXT NOT NULL,
                    line_start INTEGER NOT NULL, line_end INTEGER NOT NULL,
                    start_offset INTEGER NOT NULL, end_offset INTEGER NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts
                    USING fts5(body, tokenize='porter unicode61 remove_diacritics 2');
                CREATE TRIGGER IF NOT EXISTS chunks_insert AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunk_fts(rowid, body) VALUES(new.id,new.body);
                END;
                CREATE TRIGGER IF NOT EXISTS chunks_delete AFTER DELETE ON chunks BEGIN
                    DELETE FROM chunk_fts WHERE rowid=old.id;
                END;
            """)
            db.commit()

    @staticmethod
    def _metadata(row) -> dict:
        return {
            "id": row["id"],
            "filename": row["filename"],
            "title": row["title"],
            "bytes": row["bytes"],
            "sample": bool(row["sample"]),
            "createdAt": row["created_at"],
            "passages": row["passages"],
        }

    def list_documents(self) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("""SELECT d.*,count(c.id) AS passages FROM documents d
                LEFT JOIN chunks c ON c.document_id=d.id GROUP BY d.id
                ORDER BY d.created_at,d.id""").fetchall()
        return [self._metadata(row) for row in rows]

    def stats(self) -> dict:
        documents = self.list_documents()
        return {
            "documents": len(documents),
            "passages": sum(d["passages"] for d in documents),
            "bytes": sum(d["bytes"] for d in documents),
        }

    def _add(self, db, filename: str, content: str, sample: bool = False) -> str:
        filename, content = normalize_upload(filename, content)
        digest = hashlib.sha256(content.encode()).hexdigest()
        if db.execute("SELECT 1 FROM documents WHERE digest=?", (digest,)).fetchone():
            raise StoreError("This exact source is already in your collection.", 409)
        totals = db.execute(
            "SELECT count(*) AS count,coalesce(sum(bytes),0) AS bytes FROM documents"
        ).fetchone()
        size = len(content.encode())
        if totals["count"] >= 30 or totals["bytes"] + size > MAX_COLLECTION_BYTES:
            raise StoreError(
                "Collection limit reached: 30 sources or 2 MiB total. Delete a source first.", 409
            )
        heading = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = (
            heading.group(1)[:120]
            if heading
            else Path(filename).stem.replace("-", " ").replace("_", " ")
        )
        document_id = uuid.uuid4().hex
        db.execute(
            "INSERT INTO documents VALUES(?,?,?,?,?,?,?,?)",
            (document_id, filename, title, content, digest, size, int(sample), time.time()),
        )
        db.executemany(
            """INSERT INTO chunks(document_id,body,heading,line_start,line_end,start_offset,end_offset)
            VALUES(?,?,?,?,?,?,?)""",
            [
                (document_id, c.text, c.heading, c.line_start, c.line_end, c.start, c.end)
                for c in chunk_text(content)
            ],
        )
        return document_id

    def add(self, filename: str, content: str) -> dict:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            document_id = self._add(db, filename, content)
            db.commit()
        return next(d for d in self.list_documents() if d["id"] == document_id)

    def document(self, document_id: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if row is None:
            raise StoreError("Source not found in this collection.", 404)
        return {
            "id": row["id"],
            "title": row["title"],
            "filename": row["filename"],
            "content": row["content"],
            "lines": row["content"].split("\n"),
            "sample": bool(row["sample"]),
        }

    def delete(self, document_id: str):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("DELETE FROM documents WHERE id=?", (document_id,)).rowcount != 1:
                raise StoreError("Source not found in this collection.", 404)
            db.commit()

    def reset_samples(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM documents")
            for filename, content in SAMPLES:
                self._add(db, filename, content, sample=True)
            db.commit()

    def search(self, query: str, document_id: str | None = None) -> dict:
        match = safe_query(query)
        if document_id is not None:
            self.document(document_id)
        where = "chunk_fts MATCH ?" + (" AND d.id=?" if document_id else "")
        params = (match, document_id) if document_id else (match,)
        with self.connection() as db:
            counts = db.execute(
                f"""SELECT count(*) AS matches,count(DISTINCT d.id) AS documents
                FROM chunk_fts JOIN chunks c ON c.id=chunk_fts.rowid
                JOIN documents d ON d.id=c.document_id WHERE {where}""",
                params,
            ).fetchone()
            rows = db.execute(
                f"""SELECT c.*,d.title,d.filename,
                snippet(chunk_fts,0,char(1),char(2),' … ',48) AS excerpt
                FROM chunk_fts JOIN chunks c ON c.id=chunk_fts.rowid
                JOIN documents d ON d.id=c.document_id WHERE {where}
                ORDER BY bm25(chunk_fts),c.id LIMIT 24""",
                params,
            ).fetchall()
        evidence = [
            {
                "rank": n + 1,
                "chunkId": row["id"],
                "documentId": row["document_id"],
                "title": row["title"],
                "filename": row["filename"],
                "heading": row["heading"],
                "lineStart": row["line_start"],
                "lineEnd": row["line_end"],
                "segments": snippet_segments(row["excerpt"]),
            }
            for n, row in enumerate(rows)
        ]
        return {
            "query": query,
            "status": "matched" if evidence else "no_match",
            "matchCount": counts["matches"],
            "documentCount": counts["documents"],
            "evidence": evidence,
            "truncated": counts["matches"] > len(evidence),
        }


@dataclass(frozen=True)
class BrowserCollection:
    key: str
    token: str
    csrf: str
    expires_at: float
    store: CollectionStore


class Registry:
    def __init__(self, directory: Path, max_collections: int = 500):
        self.directory = Path(directory)
        self.path = self.directory / "registry.sqlite3"
        self.max_collections = max_collections

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS collections(
                key TEXT PRIMARY KEY,csrf TEXT NOT NULL,created_at REAL NOT NULL,expires_at REAL NOT NULL)""")

    def _store(self, key: str) -> CollectionStore:
        if not TOKEN_PATTERN.fullmatch(key):
            raise StoreError("Invalid collection.", 401)
        return CollectionStore(self.directory / "collections" / f"{key}.sqlite3")

    def lookup(self, token: str | None, now: float | None = None) -> BrowserCollection | None:
        if not token or not TOKEN_PATTERN.fullmatch(token):
            return None
        key = hashlib.sha256(token.encode()).hexdigest()
        with self.connection() as db:
            row = db.execute(
                "SELECT csrf,expires_at FROM collections WHERE key=? AND expires_at>?",
                (key, now if now is not None else time.time()),
            ).fetchone()
        if not row or not self._store(key).path.exists():
            return None
        return BrowserCollection(key, token, row[0], row[1], self._store(key))

    def create(self, now: float | None = None) -> BrowserCollection:
        now = now if now is not None else time.time()
        token, csrf = secrets.token_hex(32), secrets.token_hex(32)
        key = hashlib.sha256(token.encode()).hexdigest()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            expired = db.execute(
                "SELECT key FROM collections WHERE expires_at<=?", (now,)
            ).fetchall()
            for (old_key,) in expired:
                for suffix in ("", "-wal", "-shm"):
                    self._store(old_key).path.with_name(f"{old_key}.sqlite3{suffix}").unlink(
                        missing_ok=True
                    )
            db.execute("DELETE FROM collections WHERE expires_at<=?", (now,))
            if db.execute("SELECT count(*) FROM collections").fetchone()[0] >= self.max_collections:
                raise StoreError("This demo is at capacity. Please try again later.", 503)
            store = self._store(key)
            store.initialize()
            store.reset_samples()
            db.execute(
                "INSERT INTO collections VALUES(?,?,?,?)", (key, csrf, now, now + SESSION_SECONDS)
            )
            db.commit()
        return BrowserCollection(key, token, csrf, now + SESSION_SECONDS, store)
