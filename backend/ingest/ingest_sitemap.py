import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from fastembed import TextEmbedding
from sqlalchemy import create_engine, text

DATABASE_URL     = os.environ["DATABASE_URL"]
SITEMAP_URL      = os.environ["SITEMAP_URL"]
CANONICAL_DOMAIN = os.environ.get("CANONICAL_DOMAIN", "https://www.petjio.in")
EXCLUDE_SUBSTRINGS = [s.strip() for s in os.environ.get("CRAWL_EXCLUDE_SUBSTRINGS", "").split(",") if s.strip()]

EMBED_DIM = 384

print("Loading model...", flush=True)
model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
print("Model ready.", flush=True)


def embed(text_in: str) -> list[float]:
    return list(model.embed([text_in]))[0].tolist()


def is_allowed(url: str) -> bool:
    u = urlparse(url)
    if u.netloc != urlparse(CANONICAL_DOMAIN).netloc:
        return False
    return not any(sub in u.path for sub in EXCLUDE_SUBSTRINGS)


def get_sitemap_urls() -> list[str]:
    xml = requests.get(SITEMAP_URL, timeout=60).text
    soup = BeautifulSoup(xml, "xml")
    urls = [loc.text.strip() for loc in soup.find_all("loc")]
    return sorted(set(u for u in urls if is_allowed(u)))


def clean_text(html: str) -> tuple[str | None, str]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    title = soup.title.text.strip() if soup.title and soup.title.text else None
    text = soup.get_text("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return title, text.strip()


def chunk_text(text: str, max_chars: int = 800, overlap: int = 150) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        if start >= len(text):
            break
    return chunks


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


def main():
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    ensure_schema(engine)
    urls = get_sitemap_urls()
    print(f"Found {len(urls)} sitemap URLs", flush=True)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM rag_chunks WHERE source = 'site_crawl';"))

    for i, url in enumerate(urls, 1):
        try:
            r = requests.get(url, timeout=45, headers={"User-Agent": "NanuAI-WebRAG/1.0"})
            r.raise_for_status()
            title, text_content = clean_text(r.text)
            print(f"[{i}/{len(urls)}] {url} | {len(text_content)} chars", flush=True)
            if len(text_content) < 200:
                print("  SKIPPED (too short)", flush=True)
                continue
            chunks = chunk_text(text_content)
            inserted = 0
            for ch in chunks:
                emb = embed(ch)
                with engine.begin() as conn:
                    conn.execute(
                        text("INSERT INTO rag_chunks(url,title,content,embedding,source) "
                             "VALUES(:url,:title,:content,:embedding,'site_crawl')"),
                        {"url": url, "title": title, "content": ch, "embedding": emb},
                    )
                inserted += 1
            print(f"  OK: {inserted} chunks", flush=True)
        except Exception as e:
            print(f"  FAILED: {e}", flush=True)

    print("\nDone.")


if __name__ == "__main__":
    main()