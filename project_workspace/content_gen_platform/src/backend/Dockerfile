FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG TARGETPLATFORM

# Install CPU-only PyTorch to avoid CUDA bloat on amd64 (~200 MB vs 2 GB).
# arm64/aarch64 wheels on PyPI are always CPU-only — no special handling needed.
COPY requirements.txt .
RUN if [ "$TARGETPLATFORM" = "linux/amd64" ]; then \
      pip install --no-cache-dir \
        "torch==2.3.1+cpu" "sentence-transformers==3.0.1" \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple; \
    else \
      pip install --no-cache-dir "torch==2.3.1" "sentence-transformers==3.0.1"; \
    fi

# Install remaining dependencies (torch already present, pip skips reinstall)
RUN grep -Ev "^(torch|sentence-transformers)==" requirements.txt | \
    pip install --no-cache-dir -r /dev/stdin

# Copy project
COPY . .

# Create directories
RUN mkdir -p /app/staticfiles /app/media

# Collect static files
RUN python manage.py collectstatic --noinput --settings=config.settings.production || true

EXPOSE 8000

CMD ["gunicorn", "config.asgi:application", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120"]
