#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# AdScope Scheduler - Termux (S9+) Setup Script
#
# 1. Install Termux from F-Droid (NOT Play Store)
# 2. Open Termux and run:
#    curl -sL https://raw.githubusercontent.com/makebestdeal-source/adscope/master/scripts/setup_s9_termux.sh | bash
#
# Or copy this file to S9+ and run: bash setup_s9_termux.sh
# ============================================================

set -e

echo "=== AdScope S9+ Termux Setup ==="

# 1. Update packages
pkg update -y && pkg upgrade -y

# 2. Install required packages
pkg install -y python git chromium nodejs-lts

# 3. Install pip dependencies
pip install --upgrade pip
pip install playwright apscheduler aiosqlite sqlalchemy loguru requests python-dotenv httpx openai Pillow openpyxl aiohttp

# 4. Install Playwright Chromium for Termux
# Termux uses its own chromium package
playwright install chromium 2>/dev/null || echo "Using system chromium"

# 5. Clone repo (or pull if exists)
REPO_DIR="$HOME/adscope"
if [ -d "$REPO_DIR" ]; then
    cd "$REPO_DIR" && git pull
else
    git clone https://github.com/makebestdeal-source/adscope.git "$REPO_DIR"
fi
cd "$REPO_DIR"

# 6. Copy .env from template if not exists
if [ ! -f .env ]; then
    cp .env.example .env 2>/dev/null || echo "Create .env manually"
    echo "EDIT .env with your API keys!"
fi

# 7. Prevent Termux from being killed by Android
echo "=== Setup wake-lock ==="
termux-wake-lock 2>/dev/null || echo "Install termux-api: pkg install termux-api"

# 8. Create start script
cat > "$HOME/start_adscope.sh" << 'STARTEOF'
#!/data/data/com.termux/files/usr/bin/bash
cd ~/adscope
termux-wake-lock
python scripts/run_scheduler.py
STARTEOF
chmod +x "$HOME/start_adscope.sh"

# 9. Setup Termux:Boot for auto-start on phone boot
mkdir -p "$HOME/.termux/boot"
cat > "$HOME/.termux/boot/start_adscope.sh" << 'BOOTEOF'
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd ~/adscope && git pull
sleep 10
python scripts/run_scheduler.py >> ~/adscope/logs/termux.log 2>&1 &
BOOTEOF
chmod +x "$HOME/.termux/boot/start_adscope.sh"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Start scheduler:  ~/start_adscope.sh"
echo "Auto-start on boot: Install Termux:Boot from F-Droid"
echo "Keep alive: termux-wake-lock (already set)"
echo ""
echo "IMPORTANT: Go to Android Settings > Battery > AdScope/Termux"
echo "  -> Disable battery optimization (unrestricted)"
echo ""
