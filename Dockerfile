FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

RUN pip install --upgrade pip && \
    pip install .

COPY . .

EXPOSE 8000

HEALTHCHECK NONE

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]