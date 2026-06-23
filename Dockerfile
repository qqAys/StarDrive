# Keep the image parser in lockstep with uv.lock (revision 3). The floating
# Python tag may be served from Docker's local cache with an older uv release.
FROM astral/uv:0.11.23-python3.12-trixie-slim
LABEL authors="jinx"

ARG APP_VERSION=unknown
LABEL org.opencontainers.image.version="${APP_VERSION}"

WORKDIR /opt/stardrive

RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g; s|http://deb.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends --fix-missing \
        -o Acquire::Retries=5 \
        -o Acquire::http::Timeout=30 \
        -o Acquire::https::Timeout=30 \
        fonts-noto-cjk \
        libreoffice \
        libreoffice-writer \
        libreoffice-calc \
        libreoffice-impress \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

COPY . .

ENV STARDRIVE_DEBUG=False
ENV STARDRIVE_LOG_LEVEL=INFO

ENV STARDRIVE_APP_DEFAULT_LANGUAGE=en-US
ENV STARDRIVE_APP_DATA_DIR=app_data

# Python优化
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN uv sync --locked --no-dev
RUN uv run --no-dev pybabel compile -d app/locales

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8080/api/healthz').read()"

CMD ["uv", "run", "--no-dev", "-m", "app.main"]
