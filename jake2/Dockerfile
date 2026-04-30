FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY core/ ./core/
COPY mcp/ ./mcp/
COPY agents/ ./agents/
COPY audits/ ./audits/
COPY api/ ./api/
COPY diagnosis/ ./diagnosis/
COPY scripts/ ./scripts/
COPY webui/ ./webui/
COPY config/ ./config/
COPY data/ ./data/
COPY jake ./jake

RUN pip install --no-cache-dir -e .

EXPOSE 8080

ENTRYPOINT ["python", "-m", "api.server"]
