# ── ACME Analytics Platform image (Python 3.12, reproducible) ───────────────
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for pyarrow/psycopg2 build wheels are already provided as wheels,
# but libpq is handy for psycopg2-binary runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the project.
COPY . .

# Non-root user for safety.
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

# Default: run the whole pipeline then keep container alive is not desired;
# specific services override the command in docker-compose.
CMD ["python", "run_pipeline.py", "all"]
