FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# The shared package holds the enums and price table both services must agree on.
COPY shared /srv/shared
RUN pip install --no-cache-dir -e /srv/shared

COPY backend /srv/backend
WORKDIR /srv/backend

RUN useradd --create-home --uid 10001 app && chown -R app:app /srv
USER app

EXPOSE 8000

# 1 worker keeps the in-process scheduler single-instance; scale with replicas
# behind a load balancer if needed (the scheduler is lock-guarded either way).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
