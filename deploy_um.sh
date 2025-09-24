# ======== CONFIG BÁSICA (podés dejarla tal cual) ========
ROOT="$HOME/tokenxllm/tokenxllm"
ACC_FILE="$HOME/.starknet_accounts/starknet_open_zeppelin_accounts.json"
ACCOUNT="dev"

# Tomar OWNER_ADDR (tu cuenta OZ) del accounts file:
OWNER_ADDR=$(jq -r '."alpha-sepolia".dev.address // ."alpha-goerli2".dev.address' "$ACC_FILE")

# Tomar RPC_URL y AIC_ADDR del .env del backend (si existen)
ENV_FILE="$ROOT/dashboard/backend/.env"
RPC_URL_ENV=$(grep -E '^[[:space:]]*RPC_URL=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '[:space:]')
AIC_ADDR_ENV=$(grep -E '^[[:space:]]*AIC_ADDR=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '[:space:]')

# Permitir override por variables de entorno exportadas
RPC_URL="${RPC_URL:-$RPC_URL_ENV}"
AIC_ADDR="${AIC_ADDR:-$AIC_ADDR_ENV}"

if [ -z "$RPC_URL" ] || [ -z "$AIC_ADDR" ] || [ -z "$OWNER_ADDR" ]; then
  echo "Falta alguna variable:"
  echo "  RPC_URL=$RPC_URL"
  echo "  AIC_ADDR=$AIC_ADDR"
  echo "  OWNER_ADDR=$OWNER_ADDR"
  echo "Revisá $ENV_FILE y/o exportá RPC_URL y AIC_ADDR en el shell."
  exit 1
fi

echo "==> RPC_URL=$RPC_URL"
echo "==> AIC_ADDR=$AIC_ADDR"
echo "==> OWNER_ADDR=$OWNER_ADDR"

# Sanity check del RPC (debe devolver SN_SEPOLIA)
echo "> chainId:"
curl -s -X POST "$RPC_URL" -H 'content-type: application/json' \
  --data '{"jsonrpc":"2.0","method":"starknet_chainId","id":1}' && echo

# ======== COMPILAR PROYECTO (con getters nuevos) ========
cd "$ROOT" || exit 1
scarb --release build
cp -f target/release/tokenxllm.starknet_artifacts.json target/release/starknet_artifacts.json
echo "> Contratos en build:"; jq -r '.contracts[] | .name' target/release/starknet_artifacts.json

# ======== DECLARE UsageManager ========
echo "> DECLARE UsageManager…"
OUT=$(sncast --account "$ACCOUNT" --accounts-file "$ACC_FILE" \
  declare --url "$RPC_URL" \
  --package tokenxllm \
  --contract-name UsageManager 2>&1)
echo "$OUT"

CLASS_HASH_UM=$(echo "$OUT" | grep -oiE 'class[ _-]?hash[: ]+0x[0-9a-f]+' | awk '{print $NF}' | tail -n1)
if [ -z "$CLASS_HASH_UM" ]; then
  echo "!! No pude extraer CLASS_HASH_UM. Abortando."
  exit 1
fi
echo "CLASS_HASH_UM=$CLASS_HASH_UM"
sleep 3000
# ======== DEPLOY UsageManager ========
FREE=3000
PRICE_LOW=10000000000000000  # 0.01 * 10^18
PRICE_HIGH=0
EPOCH=86400
TREASURY="$OWNER_ADDR"

echo "> DEPLOY UsageManager…"
OUT=$(sncast --account "$ACCOUNT" --accounts-file "$ACC_FILE" \
  deploy --url "$RPC_URL" \
  --class-hash "$CLASS_HASH_UM" \
  --constructor-calldata \
    "$AIC_ADDR" "$TREASURY" \
    $FREE $PRICE_LOW $PRICE_HIGH \
    $EPOCH "$OWNER_ADDR" 2>&1)
echo "$OUT"

UM_ADDR=$(echo "$OUT" | grep -oiE 'contract[ _-]?address[: ]+0x[0-9a-f]+' | awk '{print $NF}' | tail -n1)
if [ -z "$UM_ADDR" ]; then
  echo "!! No pude extraer UM_ADDR. Abortando."
  exit 1
fi
echo "UM_ADDR=$UM_ADDR"

# ======== ACTUALIZAR .env DEL BACKEND ========
if grep -qE '^[[:space:]]*UM_ADDR=' "$ENV_FILE" 2>/dev/null; then
  sed -i.bak -E 's|^[[:space:]]*UM_ADDR=.*|UM_ADDR='"$UM_ADDR"'|' "$ENV_FILE"
else
  echo "UM_ADDR=$UM_ADDR" >> "$ENV_FILE"
fi
echo "Actualizado $ENV_FILE con UM_ADDR=$UM_ADDR"

# ======== RESUMEN ========
echo
echo "==== RESUMEN ===="
echo "RPC_URL=$RPC_URL"
echo "AIC_ADDR=$AIC_ADDR"
echo "UM_ADDR=$UM_ADDR"
echo "================="

echo
echo "Ahora reiniciá el backend y verificá:"
echo "  uvicorn main:app --host 0.0.0.0 --port 8000"
echo "  curl -s http://localhost:8000/config | jq"
echo "  curl -s \"http://localhost:8000/free_quota?user=$OWNER_ADDR\" | jq"
