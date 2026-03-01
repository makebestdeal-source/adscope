FROM python:3.12-slim

WORKDIR /app

# System deps for supervisord
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev supervisor curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

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
