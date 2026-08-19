FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /srv/shared
RUN pip install --no-cache-dir -e /srv/shared

COPY bot /srv/bot
WORKDIR /srv/bot
RUN pip install --no-cache-dir -e .

RUN useradd --create-home --uid 10002 bot && chown -R bot:bot /srv
USER bot

CMD ["python", "-m", "gg_bot"]
