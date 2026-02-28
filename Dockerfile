FROM python:3.12-slim

WORKDIR /app

# System deps for Playwright + supervisord
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev supervisor curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Playwright Chromium
RUN playwright install chromium --with-deps

# Supervisord config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8000

# Create dirs on volume mount (runs after volume is mounted)
CMD mkdir -p /data/stored_images /data/logs && supervisord -c /etc/supervisor/conf.d/supervisord.conf
