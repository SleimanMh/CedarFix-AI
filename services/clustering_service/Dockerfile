FROM python:3.11-slim
WORKDIR /app
COPY shared /app/shared
RUN pip install --no-cache-dir --timeout 300 --retries 3 /app/shared
COPY services/clustering_service/requirements.txt .
RUN pip install --no-cache-dir --timeout 300 --retries 3 -r requirements.txt
COPY services/clustering_service/app /app/app
EXPOSE 8004
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
