FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir . \
    && playwright install --with-deps chromium

CMD ["busca-voos", "run", "--config", "/app/config.yaml"]