"""意思決定ログの永続化ストア"""

from __future__ import annotations

from typing import Protocol

import aiosqlite

from cherry_bomb.models.schemas import DecisionRecord


class DecisionStore(Protocol):
    """意思決定ログストアのプロトコル"""

    async def save(self, record: DecisionRecord) -> None: ...
    async def get(self, session_id: str) -> DecisionRecord | None: ...
    async def search(self, query: str, limit: int = 10) -> list[DecisionRecord]: ...


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS decision_records (
    session_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    user_message TEXT NOT NULL,
    channel TEXT DEFAULT '',
    user_id TEXT DEFAULT '',
    final_answer TEXT DEFAULT '',
    record_json TEXT NOT NULL
)
"""


class SQLiteDecisionStore:
    """SQLite ベースの意思決定ログストア"""

    def __init__(self, db_path: str = "data/decisions.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(_CREATE_TABLE)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            msg = "Store not initialized. Call initialize() first."
            raise RuntimeError(msg)
        return self._db

    async def save(self, record: DecisionRecord) -> None:
        db = self._ensure_db()
        await db.execute(
            """INSERT OR REPLACE INTO decision_records
               (session_id, timestamp, user_message, channel, user_id, final_answer, record_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                record.session_id,
                record.timestamp.isoformat(),
                record.user_message,
                record.channel,
                record.user_id,
                record.final_answer,
                record.model_dump_json(),
            ),
        )
        await db.commit()

    async def get(self, session_id: str) -> DecisionRecord | None:
        db = self._ensure_db()
        async with db.execute(
            "SELECT record_json FROM decision_records WHERE session_id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return DecisionRecord.model_validate_json(row[0])

    async def search(self, query: str, limit: int = 10) -> list[DecisionRecord]:
        db = self._ensure_db()
        pattern = f"%{query}%"
        async with db.execute(
            """SELECT record_json FROM decision_records
               WHERE user_message LIKE ? OR record_json LIKE ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (pattern, pattern, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [DecisionRecord.model_validate_json(row[0]) for row in rows]
