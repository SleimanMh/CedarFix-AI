FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install runtime dependencies
RUN pip install --no-cache-dir \
    fastapi==0.111.* \
    "uvicorn[standard]==0.29.*" \
    "sqlalchemy[asyncio]==2.0.*" \
    asyncpg==0.29.* \
    redis==5.0.* \
    "pydantic>=2.0" \
    sentence-transformers==3.0.*

# Pre-download the embedding model into the image layer so the container
# starts without needing internet access at runtime.
RUN python - <<'EOF'
from sentence_transformers import SentenceTransformer
SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")
EOF

COPY src/ ./src/

ENV PYTHONUNBUFFERED=1
EXPOSE 8001

CMD ["uvicorn", "src.iep1.main:app", "--host", "0.0.0.0", "--port", "8001"]
