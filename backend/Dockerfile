# Stage 1: Builder - keep source by default; optionally compile .py to .so.
FROM python:3.11 AS builder

ARG ENABLE_CYTHON=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt docker-constraints.txt ./
COPY setup_cython.py ./
COPY app ./app

RUN if [ "$ENABLE_CYTHON" = "true" ]; then \
        sed -i 's#deb.debian.org#mirrors.aliyun.com#g; s#security.debian.org#mirrors.aliyun.com#g' /etc/apt/sources.list.d/debian.sources \
        && apt-get update \
        && apt-get install -y --no-install-recommends gcc python3-dev \
        && rm -rf /var/lib/apt/lists/* \
        && pip install \
            -i https://mirrors.aliyun.com/pypi/simple/ \
            --trusted-host mirrors.aliyun.com \
            -c docker-constraints.txt \
            -r requirements.txt \
        && pip install \
            -i https://mirrors.aliyun.com/pypi/simple/ \
            --trusted-host mirrors.aliyun.com \
            cython \
        && python setup_cython.py build_ext --inplace \
        && find app -name "*.py" \
            ! -name "__init__.py" \
            ! -name "main.py" \
            ! -name "runtime.py" \
            ! -name "worker.py" \
            ! -name "script_process.py" \
            ! -path "app/services/xlsx_qa/pdf_exporter.py" \
            ! -path "app/services/xlsx_qa/ppt_exporter.py" \
            ! -path "app/services/xlsx_qa/service.py" \
            -delete \
        && find app -name "*.c" -delete; \
    else \
        echo "Skipping Cython compilation for fast deploy"; \
    fi

# Stage 2: Runtime
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    RELOAD=false \
    UVICORN_WORKERS=2

WORKDIR /app

COPY requirements.txt docker-constraints.txt ./
RUN pip install \
        -i https://mirrors.aliyun.com/pypi/simple/ \
        --trusted-host mirrors.aliyun.com \
        -c docker-constraints.txt \
        -r requirements.txt

COPY --from=builder /app/app ./app
COPY scripts ./scripts
COPY init_tables.sql ./init_tables.sql
COPY tem.pptx ./tem.pptx
COPY pptTemplate ./pptTemplate
COPY assets ./assets

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8000\")}/health', timeout=5).read()" || exit 1

CMD ["python", "-m", "app.runtime"]
