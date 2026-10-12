FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy uv binary directly from official image (zero download time)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy pyproject first for layer caching
COPY pyproject.toml .

# Install dependencies using uv with a mounted cache
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r pyproject.toml

COPY . .

EXPOSE 8000
HEALTHCHECK NONE

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]