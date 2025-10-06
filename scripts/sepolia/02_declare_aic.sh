#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

require_cmd sncast
require_cmd jq

cd "$ROOT_DIR"

echo "==> Declarando contrato tokenxllm"
OUT=$(sncast --account "$ACCOUNT_NAME" --accounts-file "$ACCOUNTS_FILE" \
  declare --url "$RPC_URL" \
  --package tokenxllm \
  --contract-name tokenxllm 2>&1)

echo "$OUT"

CLASS_HASH_AIC=$(echo "$OUT" | grep -oiE 'class[ _-]?hash[: ]+0x[0-9a-f]+' | awk '{print $NF}' | tail -n1)
if [ -z "$CLASS_HASH_AIC" ]; then
  echo "No se pudo obtener CLASS_HASH para AIC." >&2
  exit 1
fi

save_state aic_class_hash "$CLASS_HASH_AIC"
echo "CLASS_HASH_AIC=$CLASS_HASH_AIC"
