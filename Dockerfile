FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RELAY_DATA_DIR=/app/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# One image serves both halves: FastAPI answers /api/* and serves the web/ files.
COPY app ./app
COPY web ./web
COPY docs ./docs
RUN useradd --create-home --uid 10001 relay \
    && mkdir -p /app/data \
    && chown -R relay:relay /app/data

USER relay

EXPOSE 8000
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# OPENAI_API_KEY and RELAY_MODEL must be supplied at run time, never baked into the image.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
