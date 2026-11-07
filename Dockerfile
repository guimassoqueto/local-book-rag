# Keep the base image on the Python version in .tool-versions and the uv image on the uv
# version next to it.
FROM python:3.13.18-slim-trixie@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc

COPY --from=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 \
    /uv /usr/local/bin/uv

ARG APP_UID=1000
ARG APP_GID=1000

RUN groupadd --gid "$APP_GID" app \
    && useradd --uid "$APP_UID" --gid "$APP_GID" --home-dir /app --no-create-home app

WORKDIR /app

ENV UV_LINK_MODE=copy

# Dependencies first: the layer survives every change to the application code. The uv
# cache stays in a BuildKit mount: in a layer it would double the size of the image.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --all-extras --no-install-project

COPY app ./app
COPY config ./config
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --all-extras

# Created here so that the named volume mounted over .cache/huggingface inherits the owner.
RUN mkdir -p data logs .cache/huggingface && chown -R app:app data logs .cache

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface \
    TIKTOKEN_CACHE_DIR=/app/.cache/huggingface/tiktoken \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    TQDM_DISABLE=1 \
    GRADIO_ANALYTICS_ENABLED=False \
    ANONYMIZED_TELEMETRY=False

USER app

EXPOSE 7860

CMD ["book-rag", "serve"]
