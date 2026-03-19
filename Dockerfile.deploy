FROM python:3.12.9-slim

WORKDIR /app

# System deps for supervisord
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev supervisor curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Cache bust: change this value to force COPY . . to re-run with fresh adscope.db
RUN echo "FORCE_FRESH_BUILD_20260320_V9"

# Copy source code (includes adscope.db)
COPY . .

# Verify DB record count (MUST show ~32000+ records or build has wrong DB)
RUN ls -lah /app/adscope.db && python -c "import sqlite3; c=sqlite3.connect('/app/adscope.db'); print('DB ad_details count:', c.execute('SELECT COUNT(*) FROM ad_details').fetchone()[0])"

# Supervisord config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Railway: use app-bundled DB (updated on each deploy)
ENV DATABASE_URL=sqlite+aiosqlite:////app/adscope.db
ENV IMAGE_STORE_DIR=/data/stored_images
ENV PORT=8000

EXPOSE 8000

# Create image store dir, then start
CMD mkdir -p /data/stored_images /data/logs && supervisord -c /etc/supervisor/conf.d/supervisord.conf
