FROM python:3.11-slim
WORKDIR /app
COPY shared /app/shared
RUN pip install --no-cache-dir /app/shared
COPY services/review_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/review_service/app /app/app
EXPOSE 8008
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8008"]
