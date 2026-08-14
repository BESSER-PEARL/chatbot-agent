FROM python:3.12.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Agent source. config.yaml is NOT copied — the entrypoint generates it from
# environment variables at container startup (see the heredoc below).
COPY Agent_Diagram.py .
COPY system_prompt.py .
COPY translations.py  .
COPY besser_facts.md  .

# Port differs from modeling-agent (8765) to avoid conflict on the same server
EXPOSE 8766

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Generate config.yaml from environment variables at container startup
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Generate config.yaml from environment variables\n\
cat > /app/config.yaml << EOF\n\
agent:\n\
  check_transitions_delay: 5\n\
\n\
nlp:\n\
  language: en\n\
  region: US\n\
  timezone: Europe/Luxembourg\n\
  pre_processing: True\n\
  intent_threshold: 0.55\n\
  openai:\n\
    api_key: ${OPENAI_API_KEY:-}\n\
\n\
platforms:\n\
  websocket:\n\
    host: 0.0.0.0\n\
    port: 8766\n\
EOF\n\
\n\
# Append monitoring config only when a Postgres host is provided\n\
if [ -n "${POSTGRES_HOST:-}" ]; then\n\
cat >> /app/config.yaml << EOF\n\
\n\
db:\n\
  monitoring:\n\
    enabled: true\n\
    dialect: postgresql\n\
    host: ${POSTGRES_HOST}\n\
    port: ${POSTGRES_PORT:-5432}\n\
    database: ${POSTGRES_DB:-mydatabase}\n\
    username: ${POSTGRES_USER:-myuser}\n\
    password: ${POSTGRES_PASSWORD:-mypassword}\n\
EOF\n\
echo "✅ Monitoring DB configured (host: ${POSTGRES_HOST})"\n\
else\n\
echo "ℹ️  POSTGRES_HOST not set — monitoring DB disabled"\n\
fi\n\
\n\
echo "✅ config.yaml created successfully"\n\
\n\
# Run the website chat agent\n\
exec python Agent_Diagram.py\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.connect(('localhost', 8766)); s.close()" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
