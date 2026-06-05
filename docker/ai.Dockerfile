FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY shared /app/shared

# Install CPU-only torch once for all text/embedding/routing/duplicate services.
RUN pip install --no-cache-dir --timeout 300 --retries 3 torch --index-url https://download.pytorch.org/whl/cpu

COPY docker/ai-requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --timeout 300 --retries 3 -r /tmp/requirements.txt

COPY docker/run_group.py /app/docker/run_group.py
COPY services /app/services

CMD ["uvicorn", "services.text_understanding.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
