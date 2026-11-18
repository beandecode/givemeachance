# Base images pinned by digest for reproducible builds; bump deliberately (see docs/roadmap.md).

# 1) Build the React app (web/) into static files; Node never reaches the runtime image.
FROM node:24.22.0-trixie-slim@sha256:7f486cabe892bff8fef04c0f7da8dba84a560be3e4e2740b7a86afc57ebec315 AS web
WORKDIR /web
COPY web/package.json web/package-lock.json web/.npmrc ./
RUN npm ci --no-audit
COPY web/ ./
RUN npm run build -- --outDir /spa_dist --emptyOutDir

# 2) Runtime: Flask + gunicorn, serving the built app at /app.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONDONTWRITEBYTECODE=1 \
    LOG_FORMAT=json \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --require-hashes -r /app/requirements.txt

# Code stays root-owned (read-only for the app); only runtime data directories are writable.
COPY . /app
COPY --from=web /spa_dist /app/app/spa_dist
RUN useradd --system --uid 10001 --home-dir /app --no-create-home app \
    && mkdir -p /app/output /app/logs /app/output_localtest /app/logs_localtest \
    && chown app:app /app/output /app/logs /app/output_localtest /app/logs_localtest

USER app

EXPOSE 5001

# Server settings live in gunicorn.conf.py; compose files may override them with CLI flags.
CMD ["gunicorn", "run:app"]
