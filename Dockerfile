# Imagem de producao do StarHub: a mesma roda web (uvicorn), worker e beat do Celery;
# o docker-compose.yml escolhe o comando de cada container.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

# Dependencias antes do codigo: mudar so o codigo reaproveita a camada do pip.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Estaticos (com gzip/brotli do WhiteNoise) gerados na imagem. O prod.py exige estas
# variaveis; valores de mentira bastam, o collectstatic nao conecta em banco nem Redis.
RUN DJANGO_SECRET_KEY=build REDIS_URL=redis://build:6379/0 \
    POSTGRES_DB=build POSTGRES_USER=build POSTGRES_PASSWORD=build \
    python manage.py collectstatic --noinput

# Sem root: so a pasta de media (volume) e gravavel pelo app.
RUN useradd --create-home --uid 1000 starhub \
    && mkdir -p /app/media \
    && chown -R starhub:starhub /app/media
USER starhub

EXPOSE 8000
# WEB_WORKERS processos do uvicorn; --proxy-headers: o proxy (TLS) informa o IP e o https.
CMD ["sh", "-c", "uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --workers ${WEB_WORKERS:-2} --proxy-headers --forwarded-allow-ips='*'"]
