#!/usr/bin/env bash
# Deploy de AIC usando sncast (declare + deploy)
# Requiere: scarb, sncast

set -euo pipefail

# === CONFIG ===
RPC_URL="https://starknet-sepolia.public.blastapi.io/rpc/v0_9"
ACC_FILE="$HOME/.starknet_accounts/starknet_open_zeppelin_accounts.json"
ACCOUNT="dev"

CONTRACT_NAME="AIC"  # nombre del módulo en tu código: `mod AIC { ... }`
SIERRA="target/dev/tokenxllm_AIC.contract_class.json"   # artefacto Sierra esperado (solo para chequear build)
OWNER_ADDR="0x522570db5197d282febafea3538ff2deacfaf49ec85a86e30bbe45af6f7c90"

# ✅ Nombre y símbolo como FELT (hex)
NAME_HEX="0x$(echo -n "TokenXLlm Credits" | xxd -p | tr -d '\n')"
SYMBOL_HEX="0x$(echo -n "CJM" | xxd -p | tr -d '\n')"
DECIMALS=18

echo ">> Verificando build..."
[ -f "$SIERRA" ] || { echo "No existe $SIERRA. Corré: scarb build"; exit 1; }

echo ">> DECLARE $CONTRACT_NAME (sncast)"
DECLARE_OUT="$(sncast --account "$ACCOUNT" --accounts-file "$ACC_FILE" \
  declare \
  --url "$RPC_URL" \
  --contract-name "$CONTRACT_NAME" \
  | tee /dev/stderr)"

sleep 120

# Extraer class hash (admite variantes de label)
CLASS_HASH_AIC="$(echo "$DECLARE_OUT" | awk 'tolower($0) ~ /class[ _-]?hash/ {print $NF}' | tail -n1)"
if [[ -z "${CLASS_HASH_AIC:-}" ]]; then
  echo "No pude extraer CLASS_HASH automáticamente. Copialo de la salida de arriba y pegalo."
  read -rp "CLASS_HASH_AIC = " CLASS_HASH_AIC
fi
echo "CLASS_HASH_AIC: $CLASS_HASH_AIC"

echo
echo ">> DEPLOY $CONTRACT_NAME (owner = $OWNER_ADDR)"
DEPLOY_OUT="$(sncast --account "$ACCOUNT" --accounts-file "$ACC_FILE" \
  deploy \
  --url "$RPC_URL" \
  --class-hash "$CLASS_HASH_AIC" \
  --constructor-calldata "$NAME_HEX" "$SYMBOL_HEX" $DECIMALS "$OWNER_ADDR" \
  | tee /dev/stderr)"

sleep 120

# Extraer dirección del contrato (admite variantes de label)
AIC_ADDR="$(echo "$DEPLOY_OUT" | awk 'tolower($0) ~ /contract address|contract_address/ {print $NF}' | tail -n1)"

echo
echo "================ RESULT ================"
echo "AIC_ADDR: $AIC_ADDR"
echo "CLASS_HASH: $CLASS_HASH_AIC"
echo "Explorer: https://sepolia.starkscan.co/contract/$AIC_ADDR"
echo "========================================"
