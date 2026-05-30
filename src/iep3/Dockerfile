FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi==0.111.* \
    "uvicorn[standard]==0.29.*" \
    "sqlalchemy[asyncio]==2.0.*" \
    asyncpg==0.29.* \
    redis==5.0.* \
    "pydantic>=2.0"

COPY src/ ./src/
COPY data/knowledge_base/ ./data/knowledge_base/

ENV PYTHONUNBUFFERED=1
EXPOSE 8003

CMD ["uvicorn", "src.iep3.main:app", "--host", "0.0.0.0", "--port", "8003"]
