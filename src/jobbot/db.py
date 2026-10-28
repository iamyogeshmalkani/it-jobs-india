"""Storage. One SQL dialect-neutral repository over Postgres (prod) or SQLite (dev/tests).

All timestamps are unix-epoch integers so both engines behave identically. Tables are
prefixed `job_` so the bot can share a database with dealbot.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional, Sequence

STATUS_CANDIDATE = "candidate"  # passed every filter, waiting for a posting slot
STATUS_SKIPPED = "skipped"  # filtered out; `reason` says why
STATUS_POSTED = "posted"
STATUS_CLOSED = "closed"  # posted, then the job closed and the post was edited
STATUS_EXPIRED = "expired"  # a candidate that closed or aged out before it was posted

_LISTING_COLUMNS = {"status", "reason", "score", "url", "deadline", "last_seen", "text",
                    "closed_text", "keyboard", "tg_message_id", "sent_at", "closed_at"}
TABLES = ("job_listings", "job_sources", "job_kv")


class Db:
    """Thin autocommit wrapper. SQL is written with %s placeholders for both engines."""

    def __init__(self, url: str = ""):
        self.is_postgres = url.startswith(("postgres://", "postgresql://"))
        if self.is_postgres:
            import psycopg
            from psycopg.rows import dict_row

            # prepare_threshold=None keeps this working behind pgbouncer (Supabase pooler).
            self._conn = psycopg.connect(
                url, autocommit=True, row_factory=dict_row, prepare_threshold=None
            )
        else:
            path = url.replace("sqlite:///", "", 1) if url else "jobbot.db"
            self._conn = sqlite3.connect(path or ":memory:", isolation_level=None)
            self._conn.row_factory = sqlite3.Row

    def query(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        if not self.is_postgres:
            sql = sql.replace("%s", "?")
        cur = self._conn.execute(sql, tuple(params))
        if cur.description is None:
            return []
        return [dict(row) for row in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()


def _schema(is_postgres: bool) -> List[str]:
    pk = "BIGSERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    return [
        f"""CREATE TABLE IF NOT EXISTS job_listings (
            id {pk},
            source TEXT NOT NULL,
            source_job_id TEXT NOT NULL,
            dedupe_key TEXT NOT NULL,
            company_key TEXT NOT NULL,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            score INTEGER NOT NULL DEFAULT 0,
            published_at BIGINT,
            deadline BIGINT,
            first_seen BIGINT NOT NULL,
            last_seen BIGINT NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            closed_text TEXT NOT NULL DEFAULT '',
            keyboard TEXT NOT NULL DEFAULT '[]',
            raw TEXT NOT NULL,
            tg_message_id BIGINT,
            sent_at BIGINT,
            closed_at BIGINT,
            UNIQUE (source, source_job_id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_job_listings_status ON job_listings (status)",
        "CREATE INDEX IF NOT EXISTS idx_job_listings_dedupe ON job_listings (dedupe_key)",
        "CREATE INDEX IF NOT EXISTS idx_job_listings_company ON job_listings (company_key)",
        """CREATE TABLE IF NOT EXISTS job_sources (
            key TEXT PRIMARY KEY,
            last_ok_at BIGINT,
            last_count INTEGER,
            last_error TEXT
        )""",
        "CREATE TABLE IF NOT EXISTS job_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    ]


class Repo:
    def __init__(self, db: Db):
        self.db = db

    def init(self) -> None:
        for statement in _schema(self.db.is_postgres):
            self.db.query(statement)
        if self.db.is_postgres:
            # Supabase serves public-schema tables over its web API; with RLS on and no
            # policies, only our direct (owner) connection can read or write them.
            for table in TABLES:
                self.db.query(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    # --- sources -----------------------------------------------------------

    def source_last_ok(self, key: str) -> Optional[int]:
        rows = self.db.query("SELECT last_ok_at FROM job_sources WHERE key = %s", (key,))
        return int(rows[0]["last_ok_at"]) if rows and rows[0]["last_ok_at"] is not None else None

    def record_source(self, key: str, now: Optional[int], count: Optional[int],
                      error: str = "") -> None:
        """Success: pass `now` and `count`. Failure: pass None, None and the error."""
        if now is None:
            self.db.query(
                """INSERT INTO job_sources (key, last_error) VALUES (%s, %s)
                   ON CONFLICT (key) DO UPDATE SET last_error = excluded.last_error""",
                (key, error[:500]))
            return
        self.db.query(
            """INSERT INTO job_sources (key, last_ok_at, last_count, last_error)
               VALUES (%s, %s, %s, '')
               ON CONFLICT (key) DO UPDATE SET last_ok_at = excluded.last_ok_at,
                 last_count = excluded.last_count, last_error = ''""",
            (key, now, count))

    def sources(self) -> List[Dict[str, Any]]:
        return self.db.query("SELECT * FROM job_sources ORDER BY key")

    # --- listings ----------------------------------------------------------

    def get_listing(self, source: str, source_job_id: str) -> Optional[Dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM job_listings WHERE source = %s AND source_job_id = %s",
            (source, source_job_id))
        return rows[0] if rows else None

    def get(self, listing_id: int) -> Optional[Dict[str, Any]]:
        rows = self.db.query("SELECT * FROM job_listings WHERE id = %s", (listing_id,))
        return rows[0] if rows else None

    def insert_listing(self, *, source: str, source_job_id: str, dedupe_key: str,
                       company_key: str, company: str, title: str, url: str, job_type: str,
                       status: str, reason: str, score: int, published_at: Optional[int],
                       deadline: Optional[int], now: int, text: str = "",
                       raw: str, closed_text: str = "", keyboard: Optional[list] = None) -> int:
        rows = self.db.query(
            """INSERT INTO job_listings (source, source_job_id, dedupe_key, company_key, company,
                 title, url, job_type, status, reason, score, published_at, deadline, first_seen,
                 last_seen, text, closed_text, keyboard, raw)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (source, source_job_id, dedupe_key, company_key, company, title, url, job_type,
             status, reason, score, published_at, deadline, now, now, text, closed_text,
             json.dumps(keyboard or []), raw))
        return int(rows[0]["id"])

    def update(self, listing_id: int, **fields: Any) -> None:
        unknown = set(fields) - _LISTING_COLUMNS
        if unknown:
            raise ValueError(f"cannot update columns: {sorted(unknown)}")
        if "keyboard" in fields:
            fields["keyboard"] = json.dumps(fields["keyboard"])
        assignments = ", ".join(f"{col} = %s" for col in fields)
        self.db.query(f"UPDATE job_listings SET {assignments} WHERE id = %s",
                      (*fields.values(), listing_id))

    def requeue_posted(self) -> int:
        """Turn every still-open post back into a candidate so it can be posted again (used
        when the channel changes). Clears what ties it to the old channel: the message id and
        the sent time, which the duplicate and rate checks read. Closed posts stay closed.
        Returns how many jobs were re-queued."""
        n = self.db.query("SELECT COUNT(*) AS n FROM job_listings WHERE status = %s",
                          (STATUS_POSTED,))[0]["n"]
        self.db.query(
            """UPDATE job_listings SET status = %s, reason = '', sent_at = NULL,
                 tg_message_id = NULL, closed_at = NULL, text = '', closed_text = '',
                 keyboard = '[]' WHERE status = %s""",
            (STATUS_CANDIDATE, STATUS_POSTED))
        return int(n)

    def by_status(self, *statuses: str) -> List[Dict[str, Any]]:
        marks = ", ".join(["%s"] * len(statuses))
        return self.db.query(
            f"SELECT * FROM job_listings WHERE status IN ({marks}) ORDER BY score DESC, id ASC",
            statuses)

    def unseen_since(self, source: str, before_ts: int, *statuses: str) -> List[Dict[str, Any]]:
        """Listings from `source` in `statuses` that no fetch has returned since `before_ts`."""
        marks = ", ".join(["%s"] * len(statuses))
        return self.db.query(
            f"""SELECT * FROM job_listings WHERE source = %s AND last_seen < %s
                AND status IN ({marks})""",
            (source, before_ts, *statuses))

    def was_posted(self, column: str, value: str, since_ts: int) -> bool:
        if column not in ("dedupe_key", "company_key"):
            raise ValueError(column)
        rows = self.db.query(
            f"""SELECT 1 AS x FROM job_listings WHERE {column} = %s AND sent_at IS NOT NULL
                AND sent_at >= %s LIMIT 1""",
            (value, since_ts))
        return bool(rows)

    def sent_count_since(self, since_ts: int) -> int:
        rows = self.db.query(
            "SELECT COUNT(*) AS n FROM job_listings WHERE sent_at IS NOT NULL AND sent_at >= %s",
            (since_ts,))
        return int(rows[0]["n"])

    def last_sent(self) -> Optional[Dict[str, Any]]:
        rows = self.db.query(
            """SELECT sent_at, job_type FROM job_listings WHERE sent_at IS NOT NULL
               ORDER BY sent_at DESC, id DESC LIMIT 1""")
        return rows[0] if rows else None

    def counts(self) -> Dict[str, int]:
        rows = self.db.query("SELECT status, COUNT(*) AS n FROM job_listings GROUP BY status")
        return {r["status"]: int(r["n"]) for r in rows}

    def skip_reasons(self) -> Dict[str, int]:
        rows = self.db.query(
            """SELECT reason, COUNT(*) AS n FROM job_listings WHERE status = %s
               GROUP BY reason ORDER BY n DESC""", (STATUS_SKIPPED,))
        return {r["reason"]: int(r["n"]) for r in rows}

    # --- key/value ---------------------------------------------------------

    def get_kv(self, key: str) -> Optional[str]:
        rows = self.db.query("SELECT value FROM job_kv WHERE key = %s", (key,))
        return rows[0]["value"] if rows else None

    def set_kv(self, key: str, value: str) -> None:
        self.db.query(
            """INSERT INTO job_kv (key, value) VALUES (%s, %s)
               ON CONFLICT (key) DO UPDATE SET value = excluded.value""",
            (key, value))
