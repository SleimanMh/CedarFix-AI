FROM python:3.12-slim
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY iep-optimizer/requirements.txt requirements.txt
RUN pip install --no-cache-dir --timeout=120 --retries=5 -r requirements.txt
COPY data/tariff.py /app/data/tariff.py
COPY data/building_load.py /app/data/building_load.py
COPY data/grid_availability.py /app/data/grid_availability.py
COPY iep-optimizer/ /app/iep-optimizer/
WORKDIR /app/iep-optimizer
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
