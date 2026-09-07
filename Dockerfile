FROM python:3.11-slim

WORKDIR /app

# Install git, ca-certificates, AND Node.js/npm for npx-based MCP servers
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Ensure the local workspace directory for cloned repos exists
RUN mkdir -p /tmp/workspaces

COPY pyproject.toml .
COPY app/ app/

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]