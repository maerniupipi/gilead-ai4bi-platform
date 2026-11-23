ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE}
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    BATCH_HOST=0.0.0.0 BATCH_PORT=8866 BATCH_DATA_DIR=/data
WORKDIR /app
COPY requirements.lock ./
RUN pip install --index-url "${PIP_INDEX_URL}" -r requirements.lock \
    && groupadd --gid 10001 batch \
    && useradd --uid 10001 --gid batch --no-create-home batch
COPY --chown=batch:batch app ./app
USER batch
EXPOSE 8866
HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8866/healthz', timeout=4).read()"
CMD ["python", "-B", "-m", "app.main"]
