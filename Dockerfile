# Multi-stage: the frontend is built inside the image rather than copied in.
# web/dist is a build artifact and stays gitignored, so a host that builds
# from a git clone (Render, CI) has no dist/ to COPY -- building it here is
# what makes the repo self-sufficient.
FROM node:22-slim AS web
WORKDIR /web
# package files first: dependencies only reinstall when they actually change.
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY scripts ./scripts
COPY db ./db
COPY --from=web /web/dist ./web/dist

# Non-root: slim images run as root by default.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

# Render (and most PaaS) assign a port via $PORT and health-check it. Binding
# a hardcoded 8000 there fails the check even though the app started fine.
CMD ["sh", "-c", "python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
