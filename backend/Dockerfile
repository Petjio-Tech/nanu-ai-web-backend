# Stage 1 (builder): install Python dependencies and pre-cache the embedding model.
FROM python:3.11-slim AS builder

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    HF_HOME=/models

WORKDIR /app

COPY requirements.txt .

RUN python -m venv "${VIRTUAL_ENV}" \
 && pip install --upgrade pip \
 && pip install --no-cache-dir --default-timeout=1000 -r requirements.txt \
 && echo "Pre-caching sentence-transformers/all-MiniLM-L6-v2 into HF_HOME=${HF_HOME}" \
 && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Stage 2 (runtime): ship only runtime deps, application code, and cached model.
FROM python:3.11-slim AS runtime

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    HF_HOME=/models

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /models /models
COPY app ./app
COPY ingest ./ingest

EXPOSE 8000

CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]