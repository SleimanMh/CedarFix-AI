FROM python:3.12-slim
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY iep-governance/requirements.txt requirements.txt
RUN pip install --no-cache-dir --timeout=120 --retries=5 -r requirements.txt
COPY iep-governance/ /app/iep-governance/
# Governance reads forecast model metrics to self-assess drift at startup.
# Must be present in the image since cloud deployments have no host volume mounts.
COPY iep-forecast/models/ /app/iep-forecast/models/
WORKDIR /app/iep-governance
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]