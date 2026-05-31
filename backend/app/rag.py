from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from .settings import settings

import numpy as np
from sentence_transformers import SentenceTransformer


EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class RetrievedChunk:
    url: str
    title: str | None
    content: str
    score: float


class RAGStore:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.model = SentenceTransformer(EMBED_MODEL_NAME)

    def embed(self, text_in: str) -> list[float]:
        v = self.model.encode([text_in], normalize_embeddings=True)[0]
        return v.astype(np.float32).tolist()

    def ensure_schema(self):
        with self.engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS rag_chunks (
                      id bigserial PRIMARY KEY,
                      url text NOT NULL,
                      title text,
                      content text NOT NULL,
                      embedding vector(384) NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
                      ON rag_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

                    CREATE TABLE IF NOT EXISTS chat_messages (
                      id bigserial PRIMARY KEY,
                      session_id text NOT NULL,
                      role text NOT NULL CHECK (role IN ('user', 'assistant')),
                      content text NOT NULL,
                      created_at timestamptz NOT NULL DEFAULT now()
                    );
                    CREATE INDEX IF NOT EXISTS chat_messages_session_idx
                      ON chat_messages (session_id);
                    CREATE INDEX IF NOT EXISTS chat_messages_created_at_idx
                      ON chat_messages (created_at);
                    """
                )
            )
        self.cleanup_expired_messages()

    def cleanup_expired_messages(self, ttl_hours: int = 24):
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM chat_messages WHERE created_at < now() - (interval '1 hour' * :ttl)"),
                {"ttl": ttl_hours},
            )

    def is_session_expired(self, session_id: str, ttl_hours: int = 24) -> bool:
        with self.engine.begin() as conn:
            last_created_at = conn.execute(
                text("SELECT MAX(created_at) FROM chat_messages WHERE session_id = :session_id"),
                {"session_id": session_id},
            ).scalar()

        if last_created_at is None:
            return False
        if last_created_at.tzinfo is None:
            last_created_at = last_created_at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last_created_at) > timedelta(hours=ttl_hours)

    def get_recent_messages(self, session_id: str, limit: int = 10) -> list[tuple[str, str]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT role, content
                    FROM (
                      SELECT role, content, created_at, id
                      FROM chat_messages
                      WHERE session_id = :session_id
                      ORDER BY created_at DESC, id DESC
                      LIMIT :limit
                    ) recent
                    ORDER BY created_at ASC, id ASC
                    """
                ),
                {"session_id": session_id, "limit": limit},
            ).fetchall()

        return [(r[0], r[1]) for r in rows]

    def add_message(self, session_id: str, role: str, content: str):
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO chat_messages (session_id, role, content)
                    VALUES (:session_id, :role, :content)
                    """
                ),
                {"session_id": session_id, "role": role, "content": content},
            )

    def query(self, q: str, top_k: int) -> list[RetrievedChunk]:
        q_emb = self.embed(q)

        # Convert python list -> pgvector literal string, e.g. "[0.1,0.2,...]"
        q_emb_vec = "[" + ",".join(f"{x:.8f}" for x in q_emb) + "]"

        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT url, title, content,
                        1 - (embedding <=> (:q_emb)::vector) AS score
                    FROM rag_chunks
                    ORDER BY embedding <=> (:q_emb)::vector
                    LIMIT :k
                    """
                ),
                {"q_emb": q_emb_vec, "k": top_k},
            ).fetchall()

        return [RetrievedChunk(url=r[0], title=r[1], content=r[2], score=float(r[3])) for r in rows]


def make_engine() -> Engine:
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)