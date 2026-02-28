FROM python:3.12-slim

WORKDIR /app

# System deps for Playwright + supervisord
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev supervisor curl && rm -rf /var/lib/apt/lists/*

# Upgrade pip/setuptools first
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy full source (needed for pyproject.toml build)
COPY . .

# Install dependencies
RUN pip install --no-cache-dir .

# Playwright Chromium
RUN playwright install chromium --with-deps

# Data directory (Railway Volume mount point)
RUN mkdir -p /data/stored_images /data/logs

# Supervisord config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8000

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
