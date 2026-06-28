# VPS-Image (Abfrage-Seite): CPU-only, schlank. Für die GPU-Erstellen-Seite
# auf dem Laptop dient stattdessen deploy/Dockerfile.cuda.
FROM python:3.11-slim

# Keine .pyc, ungepufferte Logs (strukturiert über structlog).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/cache/huggingface

WORKDIR /app

# Abhängigkeiten zuerst (besseres Layer-Caching). CPU-Torch zuerst, damit nicht
# die großen CUDA-Wheels gezogen werden (der VPS rechnet auf CPU).
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY mykb/ mykb/
COPY scripts/ scripts/
COPY server/ server/

# Modell-Cache und Daten werden als Volumes gemountet (siehe docker-compose.yml).
VOLUME ["/data", "/cache"]

EXPOSE 8000

# Default: MCP-Server starten. Indexierung via
#   docker compose run --rm mcp python -m mykb index --source all
CMD ["python", "server/server.py"]
