#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
STATE_DIR="$SCRIPT_DIR/.cache"
mkdir -p "$STATE_DIR"

ACCOUNTS_FILE="${ACCOUNTS_FILE:-$HOME/.starknet_accounts/starknet_open_zeppelin_accounts.json}"
ACCOUNT_NAME="${ACCOUNT_NAME:-dev}"
NETWORK_KEY="${NETWORK_KEY:-alpha-sepolia}"
ENV_FILE_BACKEND="$ROOT_DIR/dashboard/backend/.env"

load_backend_env() {
  local key="$1"
  [ -f "$ENV_FILE_BACKEND" ] || return 1
  local value
  value=$(grep -E "^[[:space:]]*$key=" "$ENV_FILE_BACKEND" | tail -1 | cut -d= -f2-)
  value="${value//[$'\t\r\n ']}"
  [ -n "$value" ] || return 1
  printf '%s' "$value"
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Falta el comando '$cmd'. Instalalo antes de continuar." >&2
    exit 1
  fi
}

save_state() {
  local key="$1"
  local value="$2"
  printf '%s' "$value" > "$STATE_DIR/$key"
}

load_state() {
  local key="$1"
  local file="$STATE_DIR/$key"
  [ -f "$file" ] || return 1
  cat "$file"
}

update_backend_env() {
  local key="$1"
  local value="$2"
  mkdir -p "$(dirname "$ENV_FILE_BACKEND")"
  if [ -f "$ENV_FILE_BACKEND" ] && grep -qE "^[[:space:]]*$key=" "$ENV_FILE_BACKEND"; then
    sed -i.bak -E "s|^[[:space:]]*$key=.*|$key=$value|" "$ENV_FILE_BACKEND"
    rm -f "$ENV_FILE_BACKEND.bak"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE_BACKEND"
  fi
}

RPC_URL="${RPC_URL:-$(load_backend_env RPC_URL 2>/dev/null || true)}"
if [ -z "$RPC_URL" ]; then
  RPC_URL="https://starknet-sepolia.public.blastapi.io/rpc/v0_9"
fi

OWNER_ADDR="${OWNER_ADDR:-}"
if [ -z "$OWNER_ADDR" ] && command -v jq >/dev/null 2>&1 && [ -f "$ACCOUNTS_FILE" ]; then
  OWNER_ADDR=$(jq -r --arg net "$NETWORK_KEY" --arg acc "$ACCOUNT_NAME" '.[$net][$acc].address // empty' "$ACCOUNTS_FILE")
fi

if [ -z "$OWNER_ADDR" ]; then
  echo "Definí OWNER_ADDR en el entorno o verificá $ACCOUNTS_FILE para la cuenta '$ACCOUNT_NAME'." >&2
  exit 1
fi
