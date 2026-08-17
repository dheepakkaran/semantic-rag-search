#!/usr/bin/env bash
#
# Bare Ubuntu instance -> running stack.
#
#   sudo bash deploy/setup.sh
#
# Safe to run twice: every step checks whether it has already been done. That
# matters because this is the script you run again after recreating the
# instance from a snapshot.
#
# What it does:
#   1. adds swap, so building the Python image does not run the box out of RAM
#   2. installs Docker from Docker's own apt repository
#   3. makes sure .env exists and has a key in it
#   4. builds and starts the stack, published on port 80

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SWAP_FILE=/swapfile
SWAP_SIZE=2G

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run with sudo: sudo bash deploy/setup.sh"

# ── 1. swap ──────────────────────────────────────────────────────────────────
# The python-service image installs torch, which is ~500 MB and peaks well
# above what a 2 GB instance has spare. Without swap the build is killed.
if [[ $(swapon --show --noheadings | wc -l) -gt 0 ]]; then
  log "swap already present, skipping"
else
  log "adding ${SWAP_SIZE} swap"
  fallocate -l "$SWAP_SIZE" "$SWAP_FILE" || dd if=/dev/zero of="$SWAP_FILE" bs=1M count=2048
  chmod 600 "$SWAP_FILE"
  mkswap "$SWAP_FILE"
  swapon "$SWAP_FILE"
  grep -q "^${SWAP_FILE}" /etc/fstab || echo "${SWAP_FILE} none swap sw 0 0" >> /etc/fstab
fi

# ── 2. docker ────────────────────────────────────────────────────────────────
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  log "docker already installed, skipping"
else
  log "installing docker"
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg

  install -m 0755 -d /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
  fi

  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list

  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin

  systemctl enable --now docker
fi

# ── 3. configuration ─────────────────────────────────────────────────────────
cd "$REPO_DIR"

if [[ ! -f .env ]]; then
  log "creating .env from the example"
  cp .env.example .env
  echo "WEB_PORT=80" >> .env
fi

grep -q '^WEB_PORT=' .env || echo "WEB_PORT=80" >> .env

if ! grep -qE '^GEMINI_API_KEY=.+' .env; then
  cat <<'MSG'

  .env has no GEMINI_API_KEY yet. Add it before starting:

      nano .env          # set GEMINI_API_KEY=... and LLM_PROVIDER=gemini

  Then run this script again. Search still works without a key; only the
  grounded-answer endpoint needs one.

MSG
  die "GEMINI_API_KEY is not set in .env"
fi

# ── 4. start ─────────────────────────────────────────────────────────────────
# -f names the base file explicitly, which skips docker-compose.override.yaml
# and its development-only published ports.
log "building and starting (first build takes 5-10 minutes)"
docker compose -f docker-compose.yaml up -d --build

log "waiting for the stack to report healthy"
for _ in $(seq 1 60); do
  if curl -fsS localhost/api/health >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

PUBLIC_IP="$(curl -fsS --max-time 5 https://checkip.amazonaws.com 2>/dev/null || echo '<your-instance-ip>')"

log "done"
cat <<MSG

  Open:  http://${PUBLIC_IP%$'\n'}

  Useful:
    docker compose -f docker-compose.yaml ps
    docker compose -f docker-compose.yaml logs -f python-service
    docker compose -f docker-compose.yaml down          # stop, keep data
    docker compose -f docker-compose.yaml down -v       # stop, wipe data

MSG
