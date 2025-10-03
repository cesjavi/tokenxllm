#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

require_cmd sncast
require_cmd jq

cd "$ROOT_DIR"

echo "==> Declarando contrato UsageManager"
OUT=$(sncast --account "$ACCOUNT_NAME" --accounts-file "$ACCOUNTS_FILE" \
  declare --url "$RPC_URL" \
  --package tokenxllm \
  --contract-name UsageManager 2>&1)

echo "$OUT"

CLASS_HASH_UM=$(echo "$OUT" | grep -oiE 'class[ _-]?hash[: ]+0x[0-9a-f]+' | awk '{print $NF}' | tail -n1)
if [ -z "$CLASS_HASH_UM" ]; then
  echo "No se pudo obtener CLASS_HASH para UsageManager." >&2
  exit 1
fi

save_state um_class_hash "$CLASS_HASH_UM"
echo "CLASS_HASH_UM=$CLASS_HASH_UM"
