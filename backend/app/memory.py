import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass
class ChatTurn:
    role: str
    content: str


class ChatMemory:
    def __init__(self, engine: Engine):
        self.engine = engine

    def ensure_schema(self):
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS chat_sessions (
                      id text PRIMARY KEY,
                      created_at timestamptz NOT NULL DEFAULT now(),
                      last_active_at timestamptz NOT NULL DEFAULT now()
                    );

                    CREATE TABLE IF NOT EXISTS chat_messages (
                      id bigserial PRIMARY KEY,
                      session_id text NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                      role text NOT NULL CHECK (role IN ('user', 'assistant')),
                      content text NOT NULL,
                      created_at timestamptz NOT NULL DEFAULT now()
                    );

                    CREATE INDEX IF NOT EXISTS chat_messages_session_idx
                      ON chat_messages (session_id, created_at);
                    """
                )
            )

    def get_or_create_session(self, session_id: str | None) -> str:
        sid = session_id or str(uuid.uuid4())
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO chat_sessions (id) VALUES (:sid)
                    ON CONFLICT (id) DO UPDATE SET last_active_at = now()
                    """
                ),
                {"sid": sid},
            )
        return sid

    def get_recent_turns(self, session_id: str, max_turns: int = 4) -> list[ChatTurn]:
        """Returns up to `max_turns` user+assistant pairs, oldest first."""
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT role, content FROM (
                        SELECT role, content, created_at
                        FROM chat_messages
                        WHERE session_id = :sid
                        ORDER BY created_at DESC
                        LIMIT :n
                    ) recent
                    ORDER BY created_at ASC
                    """
                ),
                {"sid": session_id, "n": max_turns * 2},
            ).fetchall()
        return [ChatTurn(role=r[0], content=r[1]) for r in rows]

    def add_message(self, session_id: str, role: str, content: str):
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO chat_messages (session_id, role, content) VALUES (:sid, :role, :content)"
                ),
                {"sid": session_id, "role": role, "content": content},
            )
