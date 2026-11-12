#!/usr/bin/env bash
# =========================================================================
# FailoverLab: Instant Public Demo via Cloudflare Tunnel (Linux / macOS)
# =========================================================================
set -e

PORT=3000

echo "[*] Checking if FailoverLab is running on port $PORT..."
if curl -s -f -o /dev/null "http://localhost:$PORT"; then
    echo "[OK] FailoverLab is healthy on http://localhost:$PORT"
else
    echo "[!] Warning: http://localhost:$PORT is not responding yet. Ensure 'docker compose up -d' is running."
fi

# Check for cloudflared
if ! command -v cloudflared &> /dev/null; then
    echo "[*] cloudflared not found in PATH. Downloading standalone binary..."
    OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
    ARCH="$(uname -m)"
    if [ "$ARCH" = "x86_64" ]; then ARCH="amd64"; fi
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then ARCH="arm64"; fi

    BIN_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-${OS}-${ARCH}"
    mkdir -p "$(dirname "$0")/bin"
    CLOUDFLARED_BIN="$(dirname "$0")/bin/cloudflared"
    curl -L "$BIN_URL" -o "$CLOUDFLARED_BIN"
    chmod +x "$CLOUDFLARED_BIN"
else
    CLOUDFLARED_BIN="cloudflared"
fi

echo ""
echo "========================================================================="
echo "  Launching Public HTTPS Tunnel for Professor / Evaluator Demonstration  "
echo "========================================================================="
echo "Look for the public URL ending with: .trycloudflare.com"
echo ""

"$CLOUDFLARED_BIN" tunnel --url "http://localhost:$PORT"

