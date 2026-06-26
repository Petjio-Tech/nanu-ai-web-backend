import os
import re
import requests
from fastembed import TextEmbedding
from sqlalchemy import create_engine, text

DATABASE_URL  = os.environ["DATABASE_URL"]
LLMS_FULL_URL = os.environ.get("LLMS_FULL_URL", "https://www.petjio.in/llms-full.txt")

EMBED_DIM = 384

HEADING_URL_MAP = {
    "overview":                   "https://www.petjio.in/about-us",
    "mission":                    "https://www.petjio.in/about-us",
    "vision":                     "https://www.petjio.in/about-us",
    "pet services":               "https://www.petjio.in/services",
    "nanuai":                     "https://www.petjio.in/nanu-ai",
    "petcoin":                    "https://www.petjio.in/pet-coin",
    "sos emergency services":     "https://www.petjio.in/sos",
    "pet community":              "https://www.petjio.in/community",
    "partner program":            "https://www.petjio.in/partners",
    "frequently asked questions": "https://www.petjio.in/faq",
    "important disclaimer":       "https://www.petjio.in/terms-of-service",
}

print("Loading model...", flush=True)
model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
print("Model ready.", flush=True)


def embed(text_in: str) -> list[float]:
    return list(model.embed([text_in]))[0].tolist()


def ensure_schema(engine):
    with engine.begin() as conn:
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


def parse_sections(md_text: str) -> list[tuple[str, str]]:
    parts = re.split(r"\n##\s+", md_text)
    sections = []
    for part in parts:
        lines = part.strip().split("\n", 1)
        heading = lines[0].lstrip("# ").strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if body:
            sections.append((heading, body))
    return sections


def chunk_section(heading: str, body: str, max_chars: int = 1000) -> list[tuple[str, str]]:
    block = f"{heading}\n{body}".strip()
    if len(block) <= max_chars:
        return [(heading, block)]
    sub_parts = re.split(r"\n###\s+", body)
    if len(sub_parts) > 1:
        chunks = []
        intro = sub_parts[0].strip()
        if intro:
            chunks.append((heading, f"{heading}\n{intro}"))
        for sp in sub_parts[1:]:
            lines = sp.strip().split("\n", 1)
            sub_heading = lines[0].strip()
            sub_body = lines[1].strip() if len(lines) > 1 else ""
            full_title = f"{heading} - {sub_heading}"
            chunks.append((full_title, f"{full_title}\n{sub_body}"))
        return chunks
    chunks, start = [], 0
    while start < len(block):
        end = min(len(block), start + max_chars)
        chunks.append((heading, block[start:end].strip()))
        start = end
    return chunks


def main():
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    ensure_schema(engine)

    full_text = requests.get(LLMS_FULL_URL, timeout=30).text
    sections = parse_sections(full_text)
    print(f"Parsed {len(sections)} sections", flush=True)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM rag_chunks WHERE source = 'llms_txt';"))

    inserted = 0
    for heading, body in sections:
        url = HEADING_URL_MAP.get(heading.lower(), LLMS_FULL_URL)
        for chunk_title, chunk_content in chunk_section(heading, body):
            emb = embed(chunk_content)
            with engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO rag_chunks(url,title,content,embedding,source) "
                         "VALUES(:url,:title,:content,:embedding,'llms_txt')"),
                    {"url": url, "title": chunk_title, "content": chunk_content, "embedding": emb},
                )
            inserted += 1
            print(f"  [{inserted}] {chunk_title}", flush=True)

    print(f"\nInserted {inserted} chunks from llms-full.txt")


if __name__ == "__main__":
    main()