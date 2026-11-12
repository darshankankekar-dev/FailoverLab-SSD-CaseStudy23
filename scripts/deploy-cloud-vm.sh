#!/usr/bin/env bash
# =========================================================================
# FailoverLab: Cloud VM Deployment & Setup Script (Ubuntu 22.04 / 24.04 LTS)
# =========================================================================
# Architecture Note (Academic Simulation):
# Mumbai and Singapore run as logical regional microservices inside isolated
# Docker containers on a single Ubuntu VM.
#
# Topology:
# Public Internet (Ports 80/443) -> Host Caddy (TLS Termination)
#   -> Local Loopback (127.0.0.1:3000) -> Containerized Nginx Frontend Proxy
#   -> Private Docker Bridge Network ('failover_network') -> 8 Backend Services
# =========================================================================
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run with sudo: sudo bash scripts/deploy-cloud-vm.sh"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "=== [1/6] Installing Prerequisites, Docker & Caddy ==="
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release ufw debian-keyring debian-archive-keyring apt-transport-https

# Install Docker CE if missing
if ! command -v docker &> /dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
fi

# Install Caddy web server if missing
if ! command -v caddy &> /dev/null; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -y
    apt-get install -y caddy
    systemctl enable --now caddy
fi

echo "=== [2/6] Configuring Host UFW Firewall ==="
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH Access'
ufw allow 80/tcp comment 'HTTP (Caddy Let\'s Encrypt Challenge)'
ufw allow 443/tcp comment 'HTTPS (Caddy Secure Web)'
# Ensure database and microservice ports are blocked from the internet
ufw deny 5432/tcp || true
ufw deny 5433/tcp || true
ufw deny 5434/tcp || true
ufw deny 8000/tcp || true
ufw deny 8001/tcp || true
ufw deny 8002/tcp || true
ufw deny 8003/tcp || true
ufw deny 8080/tcp || true
echo "y" | ufw enable || true

echo "=== [3/6] Configuring Production Environment (.env.production) ==="
if [ ! -f .env.production ]; then
    cp .env.production.example .env.production
    
    DB_PASSWORD="$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)"
    CLUSTER_SECRET="$(openssl rand -hex 32)"
    ADMIN_SECRET="$(openssl rand -hex 32)"
    
    sed -i "s/CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_BASE64_24/$DB_PASSWORD/g" .env.production
    sed -i "s/CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32/$CLUSTER_SECRET/g" .env.production
    sed -i "s/ADMIN_API_SECRET=/ADMIN_API_SECRET=$ADMIN_SECRET/g" .env.production
    
    chmod 600 .env.production
    echo "[OK] Generated .env.production with strong cryptographic secrets (chmod 600)."
else
    echo "[*] Existing .env.production found. Preserving secrets."
fi

echo "=== [4/6] Deploying Caddy Configuration ==="
if [ -f Caddyfile ]; then
    cp Caddyfile /etc/caddy/Caddyfile
    systemctl reload caddy || systemctl restart caddy
    echo "[OK] Caddyfile deployed to /etc/caddy/Caddyfile."
fi

echo "=== [5/6] Building & Starting Docker Compose Production Stack ==="
docker compose --env-file .env.production -f compose.prod.yaml up -d --build

echo "=== [6/6] Verifying Service Health ==="
sleep 8
docker compose -f compose.prod.yaml ps

echo "========================================================================="
echo "   DEPLOYMENT INITIALIZED                                                "
echo "========================================================================="
echo "Check your domain DNS pointing to this VM's public IP."
echo "View logs with: docker compose -f compose.prod.yaml logs -f"
echo "========================================================================="
