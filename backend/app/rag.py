from dataclasses import dataclass
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
                    """
                )
            )

    def query(self, q: str, top_k: int) -> list[RetrievedChunk]:
        q_emb = self.embed(q)
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT url, title, content,
                           1 - (embedding <=> :q_emb) AS score
                    FROM rag_chunks
                    ORDER BY embedding <=> :q_emb
                    LIMIT :k
                    """
                ),
                {"q_emb": q_emb, "k": top_k},
            ).fetchall()

        return [RetrievedChunk(url=r[0], title=r[1], content=r[2], score=float(r[3])) for r in rows]


def make_engine() -> Engine:
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)