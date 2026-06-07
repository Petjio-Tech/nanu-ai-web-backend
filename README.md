# nanu-ai-web-backend

## Docker image size

The backend image now uses a multi-stage Docker build in `backend/Dockerfile`:

- **Builder stage** (`python:3.11-slim`): installs dependencies and pre-caches `sentence-transformers/all-MiniLM-L6-v2`.
- **Runtime stage** (`python:3.11-slim`): copies only the virtual environment, app code, and cached Hugging Face model with `HF_HOME=/models`.

Expected backend image size is now approximately **~1.5–2 GB** (varies slightly by CPU architecture and base-image updates), instead of the previous multi-GB image.
