FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BRIEFLEDGER_DATA_DIR=/data \
    BRIEFLEDGER_COOKIE_SECURE=true \
    PORT=8000
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock \
    && groupadd --gid 10001 briefledger \
    && useradd --uid 10001 --gid briefledger --no-create-home briefledger \
    && mkdir -p /data && chown briefledger:briefledger /data
COPY briefledger ./briefledger
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/healthz', timeout=3)"
CMD ["python", "-m", "briefledger"]
