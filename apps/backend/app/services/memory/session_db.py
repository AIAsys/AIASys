"""SQLite-backed 会话消息存储。"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from app.utils.path_utils import as_system_path


class SessionDB:
    """使用 SQLite + FTS5 持久化会话消息。"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(as_system_path(str(self.db_path)))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    created_at REAL,
                    updated_at REAL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    created_at REAL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session_id_created_at
                ON messages(session_id, created_at);

                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
                USING fts5(content, content='messages', content_rowid='id');

                CREATE TRIGGER IF NOT EXISTS messages_ai
                AFTER INSERT ON messages
                BEGIN
                    INSERT INTO messages_fts(rowid, content)
                    VALUES (new.id, new.content);
                END;

                CREATE TRIGGER IF NOT EXISTS messages_ad
                AFTER DELETE ON messages
                BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, content)
                    VALUES ('delete', old.id, old.content);
                END;

                CREATE TRIGGER IF NOT EXISTS messages_au
                AFTER UPDATE ON messages
                BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, content)
                    VALUES ('delete', old.id, old.content);
                    INSERT INTO messages_fts(rowid, content)
                    VALUES (new.id, new.content);
                END;
                """)
            message_count = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            fts_count = connection.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0]
            if message_count and fts_count == 0:
                connection.execute("INSERT INTO messages_fts(messages_fts) VALUES ('rebuild')")
            connection.commit()

    def add_message(
        self,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        created_at: float | None = None,
    ) -> None:
        now = float(created_at if created_at is not None else time.time())
        normalized_content = str(content or "")
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT session_id FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO sessions (session_id, user_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (session_id, user_id, now, now),
                )
            else:
                connection.execute(
                    """
                    UPDATE sessions
                    SET user_id = ?, updated_at = ?
                    WHERE session_id = ?
                    """,
                    (user_id, now, session_id),
                )

            connection.execute(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, normalized_content, now),
            )
            connection.commit()

    def get_messages(self, session_id: str, limit: int = 100) -> list[dict]:
        if limit <= 0:
            return []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM (
                    SELECT id, session_id, role, content, created_at
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC
                """,
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_sessions(
        self,
        query: str,
        limit: int = 20,
        exclude_session_id: str | None = None,
    ) -> list[dict]:
        normalized_query = str(query or "").strip()
        if not normalized_query or limit <= 0:
            return []

        candidate_limit = max(limit * 5, limit)
        clauses = ["messages_fts MATCH ?"]
        params: list[object] = [normalized_query]
        if exclude_session_id:
            clauses.append("s.session_id != ?")
            params.append(exclude_session_id)
        params.append(candidate_limit)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    s.session_id,
                    s.user_id,
                    s.created_at,
                    s.updated_at,
                    m.created_at AS message_created_at,
                    snippet(messages_fts, 0, '[', ']', ' … ', 16) AS snippet,
                    bm25(messages_fts) AS score
                FROM messages_fts
                JOIN messages AS m ON m.id = messages_fts.rowid
                JOIN sessions AS s ON s.session_id = m.session_id
                WHERE """
                + " AND ".join(clauses)
                + """
                ORDER BY score ASC, message_created_at DESC, s.updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        results: list[dict] = []
        seen_session_ids: set[str] = set()
        for row in rows:
            session_id = str(row["session_id"])
            if session_id in seen_session_ids:
                continue
            seen_session_ids.add(session_id)
            results.append(
                {
                    "session_id": session_id,
                    "user_id": row["user_id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "snippet": row["snippet"],
                }
            )
            if len(results) >= limit:
                break

        return results

    def get_messages_after_id(
        self, last_message_id: int, session_id: str | None = None
    ) -> list[dict]:
        with self._connect() as connection:
            if session_id:
                rows = connection.execute(
                    """
                    SELECT id, session_id, role, content, created_at
                    FROM messages
                    WHERE id > ? AND session_id = ?
                    ORDER BY id ASC
                    LIMIT 1000
                    """,
                    (last_message_id, session_id),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, session_id, role, content, created_at
                    FROM messages
                    WHERE id > ?
                    ORDER BY id ASC
                    LIMIT 1000
                    """,
                    (last_message_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    def delete_session(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM messages WHERE session_id = ?",
                (session_id,),
            )
            connection.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            connection.commit()
