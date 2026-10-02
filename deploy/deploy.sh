#!/usr/bin/env bash
# One-command deploy on a fresh Ubuntu/Debian VPS (e.g. Hostinger KVM). Run from the repo root as root:
#   sudo ./deploy/deploy.sh your-domain.com
# Re-running is safe: it keeps existing secrets and data, rebuilds and restarts the stack.
set -euo pipefail

cd "$(dirname "$0")/.."
DOMAIN="${1:-}"
SCALE="${SCALE:-1.0}"

if [ "$(id -u)" -ne 0 ]; then echo "Run as root (sudo)."; exit 1; fi

set_env() { # set_env KEY VALUE: replace or append KEY=VALUE in .env (value written single-quoted)
  local key="$1" value="$2"
  if grep -qE "^${key}=" .env; then
    python3 - "$key" "$value" <<'PY'
import re, sys
key, value = sys.argv[1], sys.argv[2]
text = open(".env").read()
text = re.sub(rf"^{key}=.*$", lambda _: f"{key}='{value}'", text, flags=re.M)
open(".env", "w").write(text)
PY
  else
    printf "%s='%s'\n" "$key" "$value" >> .env
  fi
}
get_env() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e "s/^'//" -e "s/'$//" -e 's/[[:space:]]*#.*$//'; }

echo "==> Docker"
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
command -v python3 >/dev/null || (apt-get update && apt-get install -y python3)

echo "==> Configuration (.env)"
if [ ! -f .env ]; then
  cp .env.example .env
  # fresh install: real secrets instead of the demo defaults
  set_env POSTGRES_PASSWORD "$(openssl rand -hex 16)"
  set_env JWT_SECRET "$(openssl rand -hex 32)"
fi
set_env COMPOSE_FILE "docker-compose.yml:deploy/docker-compose.prod.yml"

[ -z "$DOMAIN" ] && DOMAIN="$(get_env DOMAIN || true)"
[ -z "$DOMAIN" ] && read -rp "Domain (DNS A record must point to this server): " DOMAIN
set_env DOMAIN "$DOMAIN"

if [ -z "$(get_env GEMINI_API_KEY || true)" ]; then
  read -rsp "Gemini API key (input hidden): " key; echo
  set_env GEMINI_API_KEY "$key"
fi

if [ -z "$(get_env SITE_PASSWORD_HASH || true)" ]; then
  read -rp "Site login user [demo]: " user; user="${user:-demo}"
  read -rsp "Site login password (input hidden): " pw; echo
  set_env SITE_USER "$user"
  set_env SITE_PASSWORD_HASH "$(docker run --rm caddy:2.10 caddy hash-password --plaintext "$pw")"
fi

echo "==> Database and semantic layer (first run takes a while)"
docker compose up -d postgres --wait
if [ "$(docker compose exec -T postgres psql -U "$(get_env POSTGRES_USER)" -d "$(get_env POSTGRES_DB)" -tAc \
      "select to_regclass('marts.fct_transactions') is not null")" != "t" ]; then
  SCALE="$SCALE" docker compose --profile tools run --rm seed
  docker compose --profile tools run --rm dbt build
fi

echo "==> Build and start every service"
docker compose up -d --build --wait

echo "==> Warm up Cube pre-aggregations"
docker run --rm --network host -e JWT_SECRET="$(get_env JWT_SECRET)" -v "$PWD/scripts:/w:ro" python:3.13-slim \
  sh -c "pip install -q httpx pyjwt && python /w/warmup.py --cube-url http://127.0.0.1:$(get_env CUBE_PORT || echo 4000)" || \
  echo "Warm-up did not finish; the first queries will just be slower."

echo
echo "Live at https://$DOMAIN (user: $(get_env SITE_USER)). Logs: docker compose logs -f"
