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

[ -z "$DOMAIN" ] && DOMAIN="$(get_env DOMAIN || true)"
[ -z "$DOMAIN" ] && read -rp "Domain (DNS A record must point to this server): " DOMAIN
set_env DOMAIN "$DOMAIN"

# gemini-3.5-flash was the old default and is chronically overloaded; move installs that still pin it
[ "$(get_env GEMINI_MODEL || true)" = "gemini-3.5-flash" ] && set_env GEMINI_MODEL "gemini-3.6-flash"
if [ -z "$(get_env GEMINI_API_KEY || true)" ]; then
  read -rsp "Gemini API key (input hidden): " key; echo
  set_env GEMINI_API_KEY "$key"
fi

if [ -z "$(get_env ADMIN_USERNAME || true)" ] || [ -z "$(get_env ADMIN_PASSWORD || true)" ]; then
  echo "Create the administrator account (signs in to the app and manages the other users)."
  default_user="$(get_env SITE_USER || true)"; default_user="${default_user:-admin}"
  while :; do
    read -rp "Admin username [$default_user]: " user; user="$(printf '%s' "${user:-$default_user}" | tr '[:upper:]' '[:lower:]')"
    printf '%s' "$user" | grep -Eq '^[a-z0-9][a-z0-9._-]{2,31}$' && break
    echo "3-32 characters: lowercase letters, digits, dot, dash or underscore."
  done
  read -rp "Admin full name [Administrator]: " name; name="${name:-Administrator}"; name="${name//\'/}"
  while :; do
    read -rsp "Admin password (8+ characters, input hidden): " pw; echo
    case "$pw" in *"'"*) echo "Please avoid the ' character."; continue ;; esac
    [ "${#pw}" -ge 8 ] && break
    echo "Too short."
  done
  set_env ADMIN_USERNAME "$user"
  set_env ADMIN_DISPLAY_NAME "$name"
  set_env ADMIN_PASSWORD "$pw"
fi
chmod 600 .env   # holds the admin password, API keys and secrets

echo "==> Web server (ports 80/443)"
# Another Caddy already on :80 (e.g. Hostinger's n8n template)? Then join it instead of starting our own.
PROXY="$(docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' | awk -F'\t' '$1 !~ /^governed-banking-/ && $3 ~ /:80->/ {print $1 "\t" $2; exit}')"
if [ -n "$PROXY" ]; then
  PROXY_CONTAINER="${PROXY%%$'\t'*}"; PROXY_IMAGE="${PROXY#*$'\t'}"
  case "$PROXY_IMAGE" in
    caddy*) ;;
    *) echo "Port 80 is used by $PROXY_CONTAINER ($PROXY_IMAGE), which is not Caddy. Free ports 80/443 first."; exit 1 ;;
  esac
  PROXY_NETWORK="$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}' "$PROXY_CONTAINER" | head -1)"
  CADDYFILE="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}' "$PROXY_CONTAINER")"
  if [ -z "$CADDYFILE" ]; then
    dir="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/etc/caddy"}}{{.Source}}{{end}}{{end}}' "$PROXY_CONTAINER")"
    [ -n "$dir" ] && CADDYFILE="$dir/Caddyfile"
  fi
  if [ ! -f "$CADDYFILE" ]; then echo "Could not find the Caddyfile of $PROXY_CONTAINER on this server."; exit 1; fi
  echo "Sharing $PROXY_CONTAINER (network $PROXY_NETWORK, $CADDYFILE)"
  set_env COMPOSE_FILE "docker-compose.yml:deploy/docker-compose.prod.yml:deploy/docker-compose.shared-proxy.yml"
  set_env COMPOSE_PROFILES ""
  set_env PROXY_NETWORK "$PROXY_NETWORK"
  docker rm -f governed-banking-caddy-1 >/dev/null 2>&1 || true
else
  set_env COMPOSE_FILE "docker-compose.yml:deploy/docker-compose.prod.yml"
  set_env COMPOSE_PROFILES own-proxy
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

if [ -n "$PROXY" ]; then
  echo "==> Adding $(get_env DOMAIN) to $PROXY_CONTAINER"
  BACKUP="$(python3 deploy/register_site.py "$CADDYFILE" "$(get_env DOMAIN)")"
  if docker exec "$PROXY_CONTAINER" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
    docker exec "$PROXY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile \
      || docker restart "$PROXY_CONTAINER" >/dev/null
  else
    cat "$BACKUP" > "$CADDYFILE"   # same inode, so the container sees the restore
    echo "Caddy rejected the new config; restored the original from $BACKUP:"
    docker exec "$PROXY_CONTAINER" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile 2>&1 | tail -5 || true
    exit 1
  fi
fi

echo "==> Warm up Cube pre-aggregations"
docker run --rm --network host -e JWT_SECRET="$(get_env JWT_SECRET)" -v "$PWD/scripts:/w:ro" python:3.13-slim \
  sh -c "pip install -q httpx pyjwt && python /w/warmup.py --cube-url http://127.0.0.1:$(get_env CUBE_PORT || echo 4000)" || \
  echo "Warm-up did not finish; the first queries will just be slower."

echo
echo "Live at https://$DOMAIN - sign in as $(get_env ADMIN_USERNAME), then add people under Users. Logs: docker compose logs -f"
