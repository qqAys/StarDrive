FROM astral/uv:python3.12-bookworm-slim
LABEL authors="jinx"

WORKDIR /opt/stardrive
COPY . .

ENV STARDRIVE_DEBUG=False
ENV STARDRIVE_LOG_LEVEL=INFO

ENV STARDRIVE_APP_VERSION=0.1.0
ENV STARDRIVE_APP_DEFAULT_LANGUAGE=en-US
ENV STARDRIVE_APP_DATA_DIR=app_data

# 镜像加速
ENV UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

# Python优化
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN uv sync
RUN uv run pybabel compile -d app/locales

EXPOSE 8080

CMD ["uv", "run", "-m", "app.main"]
