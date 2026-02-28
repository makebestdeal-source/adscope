FROM python:3.11-slim

WORKDIR /app

# System deps for Playwright + supervisord
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev supervisor curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir .

# Playwright Chromium
RUN playwright install chromium --with-deps

COPY . .

# Data directory (Railway Volume mount point)
RUN mkdir -p /data/stored_images /data/logs

# Supervisord config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8000

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
