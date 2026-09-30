FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=http

# RDKit's drawing module links against libXrender and libXext
RUN apt-get update \
    && apt-get install -y --no-install-recommends libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 app

USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/healthz')"

CMD ["rdkit-mcp"]
