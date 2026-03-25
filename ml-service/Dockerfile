# ── ML Service (Container 2) ──
# Two-phase workflow:
#   1. Train models locally: python -m training.prepare_data && train_demand && train_departure
#   2. Build image with trained artifacts baked in
#
# The docker-compose.yml mounts ./data:/data for training.
# Pre-trained artifacts in artifacts/ are copied into the image.

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY training/ training/

# Copy pre-trained model artifacts (train locally first, then build)
COPY artifacts/ artifacts/

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
