import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple


class BotDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS processed_events (
                    event_id TEXT PRIMARY KEY,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def add_message(self, user_id: str, chat_id: str, role: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (user_id, chat_id, role, content)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, chat_id, role, content),
            )

    def get_recent_messages(self, user_id: str, limit: int) -> List[Dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM messages
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        rows = list(reversed(rows))
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def add_task(self, user_id: str, description: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO tasks (user_id, description)
                VALUES (?, ?)
                """,
                (user_id, description),
            )
            return int(cur.lastrowid)

    def list_tasks(self, user_id: str, include_done: bool = False):
        query = """
            SELECT id, description, status, created_at, updated_at
            FROM tasks
            WHERE user_id = ?
        """
        params: Tuple[object, ...]
        if include_done:
            params = (user_id,)
        else:
            query += " AND status = 'open'"
            params = (user_id,)
        query += " ORDER BY status, id ASC"
        with self._connect() as conn:
            return conn.execute(query, params).fetchall()

    def complete_task(self, user_id: str, task_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE tasks
                SET status = 'done', updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND id = ? AND status != 'done'
                """,
                (user_id, task_id),
            )
            return cur.rowcount > 0

    def add_note(self, user_id: str, content: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO notes (user_id, content)
                VALUES (?, ?)
                """,
                (user_id, content),
            )
            return int(cur.lastrowid)

    def recent_notes(self, user_id: str, limit: int = 5):
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, content, created_at
                FROM notes
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

    def mark_event_processed(self, event_id: str) -> bool:
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO processed_events (event_id)
                    VALUES (?)
                    """,
                    (event_id,),
                )
                return True
            except sqlite3.IntegrityError:
                return False
