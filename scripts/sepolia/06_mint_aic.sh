#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

require_cmd sncast
: "${RPC_URL:?Falta RPC_URL}"
: "${OWNER_ADDR:?Falta OWNER_ADDR}"

AIC_ADDR="${AIC_ADDR:-$(load_state aic_address 2>/dev/null || true)}"
if [ -z "$AIC_ADDR" ]; then
  echo "Falta AIC_ADDR (no se encontró en state 'aic_address')." >&2
  exit 1
fi

AMOUNT="${AMOUNT:-1000000}" # 1,000,000 AIC
# u256 (18 decimales)
AMOUNT_LOW="1000000000000000000000000"
AMOUNT_HIGH="0"

echo "==> Minteando tokens AIC"
echo "Contrato AIC: $AIC_ADDR"
echo "Destinatario: $OWNER_ADDR"
echo "Cantidad: ${AMOUNT} AIC tokens"

# Verificación defensiva: el contrato en AIC_ADDR debe tener 'symbol' == 'AIC'
SYM_HEX=$(sncast call --url "$RPC_URL" --contract-address "$AIC_ADDR" --function symbol | tr -d '\r')
echo "symbol() => $SYM_HEX"
if ! echo "$SYM_HEX" | grep -qi "0x414943"; then
  echo "Advertencia: symbol() no devolvió 'AIC' (0x414943). Revisá AIC_ADDR antes de mintear." >&2
fi

sncast invoke \
  --url "$RPC_URL" \
  --contract-address "$AIC_ADDR" \
  --function "0x02f0b3c5710379609eb5495f1ecd348cb28167711b73609fe565a72734550354" \
  --calldata "$OWNER_ADDR" "$AMOUNT_LOW" "$AMOUNT_HIGH"


echo "OK. Balance ahora:"
sncast call --url "$RPC_URL" --contract-address "$AIC_ADDR" --function balanceOf --calldata "$OWNER_ADDR"
