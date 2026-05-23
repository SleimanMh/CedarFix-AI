FROM python:3.11-slim
WORKDIR /app
COPY shared /app/shared
RUN pip install --no-cache-dir /app/shared
COPY services/priority_engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/priority_engine/app /app/app
EXPOSE 8005
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
