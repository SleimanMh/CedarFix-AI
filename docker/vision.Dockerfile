FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY shared /app/shared

# Install CPU-only torch before transformers to avoid pulling CUDA wheels.
RUN pip install --no-cache-dir --timeout 300 --retries 3 torch --index-url https://download.pytorch.org/whl/cpu

COPY services/image_understanding/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --timeout 300 --retries 3 -r /tmp/requirements.txt

COPY docker/run_group.py /app/docker/run_group.py
COPY services /app/services

CMD ["uvicorn", "services.image_understanding.app.main:app", "--host", "0.0.0.0", "--port", "8002"]
