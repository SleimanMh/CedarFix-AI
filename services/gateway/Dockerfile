FROM python:3.11-slim

WORKDIR /app

# Install shared library first (layer caching)
COPY ../../shared /app/shared
RUN pip install --no-cache-dir /app/shared

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
