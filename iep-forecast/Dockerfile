FROM python:3.12-slim
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY iep-forecast/requirements.txt requirements.txt
RUN pip install --no-cache-dir --timeout=120 --retries=5 -r requirements.txt
COPY iep-forecast/ /app/iep-forecast/
WORKDIR /app/iep-forecast
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
