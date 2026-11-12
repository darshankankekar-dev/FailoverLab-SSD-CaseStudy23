# =========================================================================
# FailoverLab: Instant Public Demo via Cloudflare Tunnel
# Runs a free, secure HTTPS tunnel to your running local FailoverLab instance.
# No credit card, no account, no open router ports needed.
# =========================================================================

$ErrorActionPreference = "Stop"

$port = 3000
$cloudflaredDir = Join-Path $PSScriptRoot "bin"
$cloudflaredExe = Join-Path $cloudflaredDir "cloudflared.exe"

# 1. Verify FailoverLab is running on port 3000
Write-Host "Checking if FailoverLab is running on port $port..." -ForegroundColor Cyan
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:$port" -UseBasicParsing -TimeoutSec 3
    Write-Host "[OK] FailoverLab is healthy and responding on http://localhost:$port" -ForegroundColor Green
} catch {
    Write-Host "[WARNING] Could not reach http://localhost:$port. Make sure your Docker Compose stack is running:" -ForegroundColor Yellow
    Write-Host "docker-compose up -d" -ForegroundColor Yellow
}

# 2. Check if cloudflared is installed or present locally
if (-not (Test-Path $cloudflaredExe)) {
    $existing = Get-Command "cloudflared" -ErrorAction SilentlyContinue
    if ($existing) {
        $cloudflaredExe = $existing.Source
    } else {
        Write-Host "cloudflared binary not found. Downloading official portable release from Cloudflare..." -ForegroundColor Cyan
        New-Item -ItemType Directory -Path $cloudflaredDir -Force | Out-Null
        $downloadUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        Invoke-WebRequest -Uri $downloadUrl -OutFile $cloudflaredExe -UseBasicParsing
        Write-Host "[OK] Downloaded cloudflared to $cloudflaredExe" -ForegroundColor Green
    }
}

Write-Host "`n=========================================================================" -ForegroundColor Magenta
Write-Host "  Launching Public HTTPS Tunnel for Professor / Evaluator Demonstration  " -ForegroundColor Magenta
Write-Host "=========================================================================`n" -ForegroundColor Magenta
Write-Host "Starting tunnel to http://localhost:$port..." -ForegroundColor Cyan
Write-Host "Look for the public URL below ending with: .trycloudflare.com`n" -ForegroundColor Yellow

& $cloudflaredExe tunnel --url "http://localhost:$port"

