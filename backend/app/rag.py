from dataclasses import dataclass
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from fastembed import TextEmbedding
from .settings import settings

EMBED_DIM = 384
_model = None


def get_model() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    return _model


def embed(text_in: str) -> list[float]:
    model = get_model()
    result = list(model.embed([text_in]))
    return result[0].tolist()


@dataclass
class RetrievedChunk:
    url: str
    title: str | None
    content: str
    score: float


class RAGStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def embed(self, text_in: str) -> list[float]:
        return embed(text_in)

    def ensure_schema(self):
        with self.engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS rag_chunks (
                  id bigserial PRIMARY KEY,
                  url text NOT NULL,
                  title text,
                  content text NOT NULL,
                  embedding vector({EMBED_DIM}) NOT NULL,
                  source text NOT NULL DEFAULT 'site_crawl'
                );
                CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
                  ON rag_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
            """))
            conn.execute(text(
                "ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'site_crawl';"
            ))

    def query(self, q: str, top_k: int) -> list[RetrievedChunk]:
        q_emb = self.embed(q)
        q_emb_vec = "[" + ",".join(f"{x:.8f}" for x in q_emb) + "]"
        with self.engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT url, title, content,
                        1 - (embedding <=> (:q_emb)::vector) AS score
                    FROM rag_chunks
                    ORDER BY embedding <=> (:q_emb)::vector
                    LIMIT :k
                """),
                {"q_emb": q_emb_vec, "k": top_k},
            ).fetchall()
        return [RetrievedChunk(url=r[0], title=r[1], content=r[2], score=float(r[3])) for r in rows]


def make_engine() -> Engine:
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)