# API image. Must build for linux/arm64 (Oracle Cloud Ampere A1 target) --
# see DEPLOY.md. Build with:
#   docker buildx build --platform linux/arm64 -t rag-api:arm64 .
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY scripts ./scripts
COPY db ./db
COPY web/dist ./web/dist

# Non-root: slim images run as root by default.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
