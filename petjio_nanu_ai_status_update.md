# Petjio Nanu AI Backend — Status Update

## 1. The Problem We Found

Nanu AI's backend (FastAPI + pgvector + Gemini) was working end-to-end — but answers to questions like *"What is Pet Coin?"* were poor.

**Root cause:** the website is a React single-page app (SPA). Page titles and content are set client-side, inside `useEffect()`, after the initial page load. Our content crawler (`ingest_sitemap.py`) was using a plain HTTP request, which only sees the page *before* React renders it — generic boilerplate instead of real content.

```
Browser sees:   "Pet Coin - India's First Pet Loyalty Program | Petjio"
Crawler saw:    "Petjio | Pet Care App in India for Verified Services"
```

As a result, the RAG database was indexing navigation menus and footer text instead of actual page content, so the AI had nothing meaningful to retrieve and answer from.

## 2. The Fix: `llms.txt` / `llms-full.txt`

Instead of (or ahead of) building a heavier fix to render JavaScript during crawling, we adopted the emerging **`llms.txt` standard** — a plain static text file convention designed specifically for AI/LLM consumption of a website.

**What was deployed (web side, already live):**
- `https://www.petjio.in/llms.txt` — short summary: what Petjio is, primary pages, core topics, products
- `https://www.petjio.in/llms-full.txt` — full structured knowledge base: Mission, Vision, all Services, NanuAI, PetCoin, SOS, Community, Partner Program, FAQ, Disclaimer

These required **no React changes, no new routes, no rebuild of the SEO/rendering pipeline** — just two static files in `public/`. Verified live and serving correct content.

**Why this matters for RAG specifically:** this file is hand-written, clean, and already organized by topic with clear headings — a far better ingestion source than scraping rendered HTML pages full of nav/footer noise.

## 3. Backend Integration (in progress)

To make the backend actually use this new source:

| Change | File | Purpose |
|---|---|---|
| Add `source` column to `rag_chunks` table | `rag.py`, `ingest_sitemap.py` | Lets two ingestion jobs (site crawl vs. `llms.txt`) coexist without overwriting each other |
| New ingestion script | `ingest/ingest_llms.py` *(new)* | Fetches `llms-full.txt`, splits it by `##` heading into clean topical chunks, embeds and stores each with a mapped canonical URL (e.g. the "PetCoin" section → `/pet-coin`) |
| Scope existing crawler to its own rows | `ingest_sitemap.py` | Changed `TRUNCATE TABLE` → `DELETE WHERE source = 'site_crawl'`, and tagged inserted rows accordingly |

**Result:** core product/service Q&A (PetCoin, NanuAI, services, FAQ, community, partners) now has high-quality, structured retrieval — achieved without needing to solve JavaScript rendering at all.

## 4. Current Status

✅ FastAPI backend, Gemini integration, pgvector, Docker — all working
✅ `llms.txt` / `llms-full.txt` deployed and verified live
✅ Backend schema + new ingestion script designed for the `llms.txt` source
🔧 Wiring the new ingestion script into the deployed backend — in progress
⏳ Blog & News content still needs the JS-rendering crawl fix (Playwright), since those pages have unique per-article content not covered by `llms-full.txt`
⏳ Conversation/session memory — not yet implemented
⏳ Production hardening (retrieval thresholds, rate limiting, logging, health checks) — not yet implemented

## 5. Why This Approach

The original plan was to fix the SPA crawling problem with browser automation (Playwright) across the entire site — a non-trivial infrastructure change (larger Docker image, headless browser in production, slower ingestion). Adopting `llms.txt` solved the most important part of the problem — accurate answers about core products and services — with a two-file static deployment instead. Browser-based rendering is now only needed for the lower-priority Blog/News sections, not as a blocker for the whole project.

## 6. Next Steps

1. Deploy the `ingest_llms.py` script and schema change; re-run ingestion
2. Verify answer quality on key questions (PetCoin, NanuAI, services)
3. Scope a Playwright-based crawl to Blog/News pages only
4. Add session memory for multi-turn conversations
5. Add production hardening (retrieval score threshold, source dedup, logging, rate limiting, health endpoint)
