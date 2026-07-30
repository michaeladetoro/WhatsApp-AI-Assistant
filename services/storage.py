import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta, date

import asyncpg

from brain.config import DATABASE_URL, HISTORY_LIMIT

logger = logging.getLogger("RAGBot.Storage")

_CREATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id         SERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_user_idx ON messages(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS kb_documents (
    id          SERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    filename    TEXT,
    source_type TEXT,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);
"""


class BotStorage:
    """
    Unified storage.

    - Session data (onboarding flags, etc.): in-memory dict — ephemeral.
    - Message history + KB documents: Postgres — persistent.
    """

    def __init__(self) -> None:
        self._pool: Optional[asyncpg.Pool] = None
        self._sessions: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Connect to Postgres and ensure schema exists."""
        if not DATABASE_URL:
            logger.warning(
                "DATABASE_URL not set — message history and KB document storage disabled. "
                "Set DATABASE_URL in .env to enable them."
            )
            return
        try:
            self._pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
            await self._ensure_schema()
            logger.info("Postgres connection pool ready.")
        except Exception as e:
            logger.error(
                f"Postgres connection failed: {e}. Running without persistent storage."
            )
            self._pool = None

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    @property
    def has_db(self) -> bool:
        return self._pool is not None

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    async def save_message(self, user_id: str, role: str, content: str) -> None:
        """Persist one message turn."""
        if not self._pool or not content:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO messages (user_id, role, content) VALUES ($1, $2, $3)",
                    user_id,
                    role,
                    content,
                )
        except Exception as e:
            logger.warning(f"save_message failed: {e}")

    async def get_history(self, user_id: str, limit: int = HISTORY_LIMIT) -> List[dict]:
        """Return the last `limit` messages for a user (oldest first)."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT role, content FROM (
                        SELECT role, content, created_at
                        FROM messages
                        WHERE user_id = $1
                        ORDER BY created_at DESC
                        LIMIT $2
                    ) sub ORDER BY created_at ASC
                    """,
                    user_id,
                    limit,
                )
            return [{"role": r["role"], "content": r["content"]} for r in rows]
        except Exception as e:
            logger.warning(f"get_history failed: {e}")
            return []

    async def clear_old_messages(self, hours: int = 4) -> int:
        """Delete messages older than `hours`. Returns number of deleted rows."""
        if not self._pool:
            return 0
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM messages WHERE created_at < NOW() - make_interval(hours => $1)",
                    hours,
                )
            deleted = int(result.split()[-1]) if result else 0
            if deleted > 0:
                logger.info(f"Cleared {deleted} old messages (older than {hours}h).")
            return deleted
        except Exception as e:
            logger.error(f"clear_old_messages failed: {e}")
            return 0

    async def clear_all_messages(self) -> int:
        """Clear all conversation messages. Returns number of deleted rows."""
        if not self._pool:
            return 0
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute("DELETE FROM messages")
            deleted = int(result.split()[-1]) if result else 0
            logger.info(f"Cleared all {deleted} conversation messages.")
            return deleted
        except Exception as e:
            logger.error(f"clear_all_messages failed: {e}")
            return 0

    # ------------------------------------------------------------------
    # Knowledge base documents
    # ------------------------------------------------------------------

    async def save_kb_document(
        self,
        title: str,
        content: str,
        filename: str = "",
        source_type: str = "",
    ) -> int:
        """
        Persist a document's extracted text to the kb_documents table.
        This is ADDITIVE — it never overwrites or deletes existing documents.

        Returns:
            The new document's database ID, or -1 if DB is unavailable.
        """
        if not self._pool:
            logger.warning("KB document not persisted — no database connection.")
            return -1
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO kb_documents (title, filename, source_type, content)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    title,
                    filename,
                    source_type,
                    content,
                )
            doc_id = row["id"]
            logger.info(f"KB document saved: id={doc_id} title='{title}'")
            return doc_id
        except Exception as e:
            logger.error(f"save_kb_document failed: {e}")
            return -1

    async def list_kb_documents(self) -> List[dict]:
        """Return metadata for all stored KB documents (no content)."""
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id, title, filename, source_type, created_at FROM kb_documents ORDER BY created_at DESC"
                )
            return [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "filename": r["filename"],
                    "source_type": r["source_type"],
                    "created_at": r["created_at"].isoformat()
                    if r["created_at"]
                    else None,
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"list_kb_documents failed: {e}")
            return []

    async def get_dashboard_analytics(self) -> dict:
        """Return basic analytics for the dashboard."""
        default_resp = {"total_messages": 0, "unique_users": 0, "total_documents": 0, "chart_data": []}
        if not self._pool:
            return default_resp
        try:
            async with self._pool.acquire() as conn:
                total_messages = await conn.fetchval("SELECT COUNT(*) FROM messages WHERE role = 'user'")
                unique_users = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM messages")
                total_documents = await conn.fetchval("SELECT COUNT(*) FROM kb_documents")
                
                chart_rows = await conn.fetch(
                    "SELECT DATE(created_at) as date, COUNT(*) as count FROM messages WHERE role = 'user' AND created_at >= NOW() - INTERVAL '6 days' GROUP BY DATE(created_at) ORDER BY DATE(created_at) ASC"
                )
                
            db_chart_data = {r["date"]: r["count"] for r in chart_rows} if chart_rows else {}
            
            today = date.today()
            chart_data = []
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                chart_data.append({
                    "date": d.isoformat(),
                    "day_label": d.strftime("%a %d/%m"),
                    "count": db_chart_data.get(d, 0)
                })

            return {
                "total_messages": total_messages or 0,
                "unique_users": unique_users or 0,
                "total_documents": total_documents or 0,
                "chart_data": chart_data,
            }
        except Exception as e:
            logger.error(f"get_dashboard_analytics failed: {e}")
            return default_resp

    async def get_all_kb_content(self) -> List[dict]:
        """
        Return all KB documents with their text content.
        Used by KBManager to rebuild the FAISS index from Postgres.
        """
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id, title, filename, content FROM kb_documents ORDER BY created_at ASC"
                )
            return [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "filename": r["filename"],
                    "content": r["content"],
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"get_all_kb_content failed: {e}")
            return []

    async def delete_kb_document(self, doc_id: int) -> Optional[str]:
        """Delete a single KB document by ID. Returns the title of the deleted document, or None if not found."""
        if not self._pool:
            return None
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "DELETE FROM kb_documents WHERE id = $1 RETURNING title", doc_id
                )
            if row:
                title = row["title"]
                logger.info(f"KB document {doc_id} ('{title}') deleted from database.")
                return title
            return None
        except Exception as e:
            logger.error(f"delete_kb_document failed: {e}")
            return None

    async def rename_kb_document(self, doc_id: int, new_filename: str) -> bool:
        """Rename a single KB document by ID. Returns True if renamed, False if not found."""
        if not self._pool:
            return False
        try:
            async with self._pool.acquire() as conn:
                status = await conn.execute(
                    "UPDATE kb_documents SET filename = $1, title = $1 WHERE id = $2", new_filename, doc_id
                )
            updated = status.startswith("UPDATE") and status != "UPDATE 0"
            if updated:
                logger.info(f"KB document {doc_id} renamed to '{new_filename}' in database.")
            return updated
        except Exception as e:
            logger.error(f"rename_kb_document failed: {e}")
            return False


    async def clear_all_kb_documents(self) -> int:
        """Delete all documents in the knowledge base. Returns number of deleted rows."""
        if not self._pool:
            return 0
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute("DELETE FROM kb_documents")
            deleted = int(result.split()[-1]) if result else 0
            logger.info(f"Cleared all {deleted} KB documents from the database.")
            return deleted
        except Exception as e:
            logger.error(f"clear_all_kb_documents failed: {e}")
            return 0

    # ------------------------------------------------------------------
    # Session cache (in-memory, ephemeral)
    # ------------------------------------------------------------------

    def get_session(self, user_id: str) -> dict:
        if user_id not in self._sessions:
            self._sessions[user_id] = {}
        return self._sessions[user_id]

    def set_session(self, user_id: str, data: dict) -> None:
        self._sessions[user_id] = data

    def has_onboarded(self, user_id: str) -> bool:
        return self._sessions.get(user_id, {}).get("onboarded", False)

    def mark_onboarded(self, user_id: str) -> None:
        self.get_session(user_id)["onboarded"] = True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _ensure_schema(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(_CREATE_SCHEMA)
        logger.info("Database schema verified.")
