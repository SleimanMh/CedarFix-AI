FROM python:3.11-slim

WORKDIR /app
COPY shared /app/shared
RUN pip install --no-cache-dir /app/shared

# Install CPU-only torch BEFORE requirements.txt so transitive deps
# (sentence-transformers) don't pull the 2GB CUDA build from PyPI.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY services/text_understanding/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/text_understanding/app /app/app
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
