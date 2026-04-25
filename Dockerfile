FROM python:3.12-slim

WORKDIR /app

# System deps for supervisord
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev supervisor curl && rm -rf /var/lib/apt/lists/*

# Install API runtime dependencies. Crawler/OCR-only packages stay in
# requirements.txt for local collection, but are intentionally excluded from
# the production API image to keep Railway deploys fast and reliable.
COPY requirements.api.txt ./
RUN pip install --no-cache-dir -r requirements.api.txt

# Copy source code
COPY . .

# Supervisord config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Railway: persistent volume config
ENV DATABASE_URL=sqlite+aiosqlite:////data/adscope.db
ENV IMAGE_STORE_DIR=/data/stored_images
ENV PORT=8000

EXPOSE 8000

# Create dirs on volume mount, then start
CMD mkdir -p /data/stored_images /data/logs && supervisord -c /etc/supervisor/conf.d/supervisord.conf
