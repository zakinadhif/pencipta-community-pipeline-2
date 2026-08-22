#!/usr/bin/env bash
# Idempotent server bootstrap + deploy for the marimo pipeline.
#
# - Idempotent: aman dijalankan berulang.
# - Menginstal cloudflared (Debian/Ubuntu) bila belum ada.
# - Menyalin .env.example ke .env bila belum ada (biar user isi rahasia).
# - build & restart container marimo + cloudflared.
#
# Penggunaan (dari server, di direktori deploy):
#   ./scripts/server_deploy.sh
#
# Variabel env yang dipakai (opsional):
#   MARIMO_PASSWORD   password marimo (default: tecnofest)
#   CF_TUNNEL_TOKEN   token Cloudflare tunnel (harus diisi sebelum cloudflared jalan)
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pencipta-community-pipeline-2}"
MARIMO_PORT="${MARIMO_PORT:-2718}"

log() { echo -e "\033[1;36m[deploy]\033[0m $*"; }
err() { echo -e "\033[1;31m[deploy]\033[0m $*" >&2; }

# --- 1. cloudflared -----------------------------------------------------------
install_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    log "cloudflared sudah terpasang: $(cloudflared --version)"
    return 0
  fi
  log "Menginstal cloudflared..."
  local arch
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64)  pkg="cloudflared-linux-amd64.deb" ;;
    aarch64|arm64) pkg="cloudflared-linux-arm64.deb" ;;
    *) err "Arsitektur tidak didukung: $arch"; return 1 ;;
  esac
  curl -fsSL -o /tmp/cloudflared.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/${pkg}"
  dpkg -i /tmp/cloudflared.deb || apt-get -f install -y
  rm -f /tmp/cloudflared.deb
  log "cloudflared terpasang: $(cloudflared --version)"
}
install_cloudflared

# --- 2. .env ---------------------------------------------------------------
if [[ ! -f "${APP_DIR}/.env" ]]; then
  log "Membuat ${APP_DIR}/.env dari .env.example (isi rahasia manual)."
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
fi

# --- 3. Pastikan data dir & volume helper -----------------------------------
mkdir -p "${APP_DIR}/data"

# --- 4. Build & restart -------------------------------------------------------
cd "${APP_DIR}"
log "Build image marimo (cache aman)..."
docker compose build marimo

log "Restart stack (marimo + cloudflared)..."
docker compose up -d --remove-orphans

log "Menunggu marimo siap di :${MARIMO_PORT}..."
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null "http://127.0.0.1:${MARIMO_PORT}/" 2>/dev/null; then
    log "marimo siap di http://127.0.0.1:${MARIMO_PORT}/"
    break
  fi
  sleep 1
done

log "Status stack:"
docker compose ps

log "Selesai. Cloudflare Tunnel token belum diisi? Jalankan:
  cd ${APP_DIR}
  docker compose up -d cloudflared   # setelah CF_TUNNEL_TOKEN diisi di .env
"
