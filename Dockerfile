# Imagem da aplicação GeoHabita (API FastAPI + frontend estático) e do pipeline de dados.
FROM python:3.12-slim

# Binário do uv copiado da imagem oficial, sem instalar nada via pip.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependências em camada própria: só é refeita quando pyproject.toml ou uv.lock mudam.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY backend/ backend/
COPY geohabita/ geohabita/
COPY frontend/ frontend/
COPY scripts/ scripts/
COPY database/ database/
COPY data/reference/ data/reference/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Usuário sem privilégios. O UID padrão 1000 coincide com o usuário comum do Linux,
# para que o pipeline consiga gravar em data/raw montado do host.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "$GID" geohabita \
    && useradd --uid "$UID" --gid "$GID" --no-create-home --shell /usr/sbin/nologin geohabita \
    && mkdir -p data/raw data/processed \
    && chown -R geohabita:geohabita data
USER geohabita

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/status', timeout=4)"]

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
