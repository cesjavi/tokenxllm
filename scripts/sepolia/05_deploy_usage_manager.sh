#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

require_cmd sncast
require_cmd jq

CLASS_HASH_UM="${CLASS_HASH_UM:-$(load_state um_class_hash 2>/dev/null || true)}"
if [ -z "$CLASS_HASH_UM" ]; then
  echo "Definí CLASS_HASH_UM o ejecutá 04_declare_usage_manager.sh antes de desplegar." >&2
  exit 1
fi

AIC_ADDR="${AIC_ADDR:-$(load_state aic_address 2>/dev/null || true)}"
if [ -z "$AIC_ADDR" ]; then
  AIC_ADDR=$(load_backend_env AIC_ADDR 2>/dev/null || true)
fi
if [ -z "$AIC_ADDR" ]; then
  echo "Definí AIC_ADDR (resultado del despliegue del token) antes de continuar." >&2
  exit 1
fi

TREASURY_ADDR="${TREASURY_ADDR:-$OWNER_ADDR}"
FREE_QUOTA="${FREE_QUOTA:-2000}"
PRICE_LOW="${PRICE_LOW:-10000000000000000}"
PRICE_HIGH="${PRICE_HIGH:-0}"
EPOCH_SECONDS="${EPOCH_SECONDS:-86400}"
ADMIN_ADDR="${ADMIN_ADDR:-$OWNER_ADDR}"

cd "$ROOT_DIR"

echo "==> Desplegando contrato UsageManager"
OUT=$(sncast --account "$ACCOUNT_NAME" --accounts-file "$ACCOUNTS_FILE" \
  deploy --url "$RPC_URL" \
  --class-hash "$CLASS_HASH_UM" \
  --constructor-calldata \
    "$AIC_ADDR" "$TREASURY_ADDR" \
    "$FREE_QUOTA" "$PRICE_LOW" "$PRICE_HIGH" \
    "$EPOCH_SECONDS" "$ADMIN_ADDR" 2>&1)

echo "$OUT"

UM_ADDR=$(echo "$OUT" | grep -oiE 'contract[ _-]?address[: ]+0x[0-9a-f]+' | awk '{print $NF}' | tail -n1)
if [ -z "$UM_ADDR" ]; then
  echo "No se pudo obtener la dirección del contrato UsageManager." >&2
  exit 1
fi

save_state um_address "$UM_ADDR"
update_backend_env UM_ADDR "$UM_ADDR"
echo "UM_ADDR=$UM_ADDR"
