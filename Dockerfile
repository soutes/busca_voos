FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir ".[web]" \
    && playwright install --with-deps chromium \
    && busca-voos init --config /app/config.yaml

CMD ["busca-voos", "painel", "--host", "0.0.0.0", "--porta", "8787", "--config", "/app/config.yaml"]