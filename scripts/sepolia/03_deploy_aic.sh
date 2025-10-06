#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

require_cmd sncast
require_cmd jq

CLASS_HASH_AIC="${CLASS_HASH_AIC:-$(load_state aic_class_hash 2>/dev/null || true)}"
if [ -z "$CLASS_HASH_AIC" ]; then
  echo "Definí CLASS_HASH_AIC o ejecutá 02_declare_aic.sh antes de desplegar." >&2
  exit 1
fi

AIC_NAME_HEX="${AIC_NAME_HEX:-0x414943}"
AIC_SYMBOL_HEX="${AIC_SYMBOL_HEX:-$AIC_NAME_HEX}"
AIC_DECIMALS="${AIC_DECIMALS:-18}"

cd "$ROOT_DIR"

echo "==> Desplegando contrato AIC"
OUT=$(sncast --account "$ACCOUNT_NAME" --accounts-file "$ACCOUNTS_FILE" \
  deploy --url "$RPC_URL" \
  --class-hash "$CLASS_HASH_AIC" \
  --constructor-calldata \
    "$AIC_NAME_HEX" "$AIC_SYMBOL_HEX" \
    "$AIC_DECIMALS" "$OWNER_ADDR" 2>&1)

echo "$OUT"

AIC_ADDR=$(echo "$OUT" | grep -oiE 'contract[ _-]?address[: ]+0x[0-9a-f]+' | awk '{print $NF}' | tail -n1)
if [ -z "$AIC_ADDR" ]; then
  echo "No se pudo obtener la dirección del contrato tokenxllm." >&2
  exit 1
fi

save_state aic_address "$AIC_ADDR"
update_backend_env AIC_ADDR "$AIC_ADDR"
echo "AIC_ADDR=$AIC_ADDR"
