import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sentence_transformers import SentenceTransformer

DATABASE_URL = os.environ["DATABASE_URL"]
SITEMAP_URL = os.environ["SITEMAP_URL"]
CANONICAL_DOMAIN = os.environ.get("CANONICAL_DOMAIN", "https://www.petjio.in")
EXCLUDE_SUBSTRINGS = [s.strip() for s in os.environ.get("CRAWL_EXCLUDE_SUBSTRINGS", "").split(",") if s.strip()]
EXCLUDE_DOMAINS = [s.strip() for s in os.environ.get("CRAWL_EXCLUDE_DOMAINS", "").split(",") if s.strip()]

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
model = SentenceTransformer(EMBED_MODEL_NAME)


def is_allowed(url: str) -> bool:
    u = urlparse(url)
    if u.netloc in EXCLUDE_DOMAINS:
        return False
    # domain lock
    canonical_host = urlparse(CANONICAL_DOMAIN).netloc
    if u.netloc != canonical_host:
        return False
    for sub in EXCLUDE_SUBSTRINGS:
        if sub in u.path:
            return False
    return True


def get_sitemap_urls() -> list[str]:
    xml = requests.get(SITEMAP_URL, timeout=60).text
    soup = BeautifulSoup(xml, "xml")
    urls = [loc.text.strip() for loc in soup.find_all("loc")]
    urls = [u for u in urls if is_allowed(u)]
    return sorted(set(urls))


def clean_text(html: str) -> tuple[str | None, str]:
    soup = BeautifulSoup(html, "lxml")

    # remove junk
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = soup.title.text.strip() if soup.title and soup.title.text else None

    text = soup.get_text("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()

    return title, text


def chunk_text(text: str, max_chars: int = 1800, overlap: int = 200) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        if start < 0:
            start = 0
        if start >= len(text):
            break
    return chunks


def embed(text_in: str) -> list[float]:
    v = model.encode([text_in], normalize_embeddings=True)[0]
    return v.tolist()


def ensure_schema(engine):
    with engine.begin() as conn:
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


def main():
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    ensure_schema(engine)

    urls = get_sitemap_urls()
    print(f"Found {len(urls)} sitemap URLs")

    # Optional: clear existing
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE rag_chunks;"))

    for i, url in enumerate(urls, 1):
        try:
            r = requests.get(url, timeout=45, headers={"User-Agent": "NanuAI-WebRAG/1.0"})
            r.raise_for_status()
            title, text_content = clean_text(r.text)

            # small skip rules
            if len(text_content) < 200:
                continue

            chunks = chunk_text(text_content)
            with engine.begin() as conn:
                for ch in chunks:
                    conn.execute(
                        text(
                            "INSERT INTO rag_chunks(url, title, content, embedding) VALUES (:url, :title, :content, :embedding)"
                        ),
                        {
                            "url": url,
                            "title": title,
                            "content": ch,
                            "embedding": embed(ch),
                        },
                    )

            print(f"[{i}/{len(urls)}] Ingested {url} ({len(chunks)} chunks)")
        except Exception as e:
            print(f"[{i}/{len(urls)}] Failed {url}: {e}")

    print("Done.")


if __name__ == "__main__":
    main()