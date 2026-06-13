FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .

# Install CPU-only PyTorch
RUN pip install \
    --no-cache-dir \
    --prefix=/install \
    torch==2.5.1 \
    --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies
RUN pip install \
    --no-cache-dir \
    --prefix=/install \
    -r requirements.txt


FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY app ./app
COPY ingest ./ingest

ENV HF_HOME=/models
ENV SENTENCE_TRANSFORMERS_HOME=/models

EXPOSE 8000

CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]