# syntax=docker/dockerfile:1

# --- stage 1: build the frontend (web/dist is gitignored, so build it here) ---
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- stage 2: runtime ---
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
# TMPDIR is a PERSISTENT path so FastEmbed's cache (tempdir/fastembed_cache) is
# baked into the image and found at runtime — never a lazy download / silent 503.
ENV PYTHONUNBUFFERED=1 \
    DATA_ROOT=/app/data \
    TMPDIR=/opt/appcache \
    PIP_NO_CACHE_DIR=1 \
    FASTEMBED_LOCAL_ONLY=1
RUN mkdir -p /opt/appcache
WORKDIR /app

COPY requirements-deploy.txt .
RUN pip install -r requirements-deploy.txt
# Prewarm the embedding model into $TMPDIR/fastembed_cache, then prove it loads
# STRICTLY OFFLINE (local_files_only=True) — the exact mode the runtime uses. If
# the baked cache is incomplete, this fails the build loudly instead of deferring
# to a network download at cold start (which could hang / 503 the demo).
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2'); print('cache populated')" && \
    python -c "from fastembed import TextEmbedding; m=TextEmbedding('sentence-transformers/all-MiniLM-L6-v2', local_files_only=True); v=list(m.embed(['warmup'])); assert v and len(v[0])==384; print('offline embedding verified', len(v[0]))"

COPY api/ api/
COPY pipeline/ pipeline/
COPY scripts/seed_qdrant.py scripts/
COPY --from=web /web/dist web/dist
COPY deploy/bundle/match-001 /app/baseline/match-001
COPY deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Build-time guard: the baseline must NOT contain a source video or match-002.
RUN if [ -e /app/baseline/match-002 ] || find /app/baseline -path '*source*' -name '*.mp4' | grep -q . ; then \
      echo "FORBIDDEN content in baseline (source video or match-002)"; exit 1; fi

EXPOSE 10000
ENTRYPOINT ["/app/entrypoint.sh"]
