FROM python:3.11-slim
WORKDIR /app
COPY shared /app/shared
RUN pip install --no-cache-dir --timeout 300 /app/shared
COPY services/monitoring_service/requirements.txt .
RUN pip install --no-cache-dir --timeout 300 -r requirements.txt
COPY services/monitoring_service/app /app/app
EXPOSE 8009
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8009"]
