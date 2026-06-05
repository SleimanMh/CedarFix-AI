FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY shared /app/shared
COPY docker/api-requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --timeout 300 --retries 3 -r /tmp/requirements.txt

COPY docker/run_group.py /app/docker/run_group.py
COPY services /app/services

CMD ["uvicorn", "services.gateway.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
