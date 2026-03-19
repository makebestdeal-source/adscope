FROM python:3.12-slim

WORKDIR /app

# System deps for supervisord
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev supervisor curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code (includes adscope.db)
COPY . .

# Verify DB record count
RUN python -c "import sqlite3; c=sqlite3.connect('/app/adscope.db'); print('ad_details:', c.execute('SELECT COUNT(*) FROM ad_details').fetchone()[0])"

# Supervisord config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Railway: use app-bundled DB (updated on each deploy)
ENV DATABASE_URL=sqlite+aiosqlite:////app/adscope.db
ENV IMAGE_STORE_DIR=/data/stored_images
ENV PORT=8000

EXPOSE 8000

# Create image store dir, then start
CMD mkdir -p /data/stored_images /data/logs && supervisord -c /etc/supervisor/conf.d/supervisord.conf
