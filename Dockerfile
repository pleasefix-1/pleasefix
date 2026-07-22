FROM python:3.12-slim-bookworm

# GeoDjango runtime libraries (GDAL pulls in GEOS + PROJ).
RUN apt-get update \
    && apt-get install -y --no-install-recommends binutils gdal-bin libgdal-dev gettext \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/venv PATH="/venv/bin:$PATH" PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project

COPY . .
RUN python manage.py compilemessages \
    && DATABASE_URL=postgis://x/x python -m django collectstatic --noinput --settings=config.settings || true

EXPOSE 8000
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3"]
