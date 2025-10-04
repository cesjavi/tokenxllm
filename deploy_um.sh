#!/usr/bin/env bash
set -euo pipefail

# === CONFIG ===
RPC_URL="https://starknet-sepolia.public.blastapi.io/rpc/v0_9"
ACC_FILE="$HOME/.starknet_accounts/starknet_open_zeppelin_accounts.json"
ACCOUNT="dev"

# Class hash del UM (el mismo que usaste antes)
CLASS_HASH_UM="0x02f0138bd302692bb1c1b01561f72f6df01a0aa09c1470a132f6837b0a26fc97"

# AIC NUEVO (salida del script anterior)
AIC_ADDR="<PEGÁ_ACÁ_TU_AIC_ADDR_NUEVO>"

# Treasury/Admin = cuenta del backend (misma que firma en Vercel)
OWNER_ADDR="0x522570db5197d282febafea3538ff2deacfaf49ec85a86e30bbe45af6f7c90"

FREE_QUOTA=3000
# price_per_unit_wei (u256) => 0.01 AIC si DECIMALS=18
PRICE_LO=10000000000000000
PRICE_HI=0
EPOCH_SECONDS=86400

echo ">> Deployando UsageManager..."
OUT=$(sncast --account "$ACCOUNT" --accounts-file "$ACC_FILE" \
  deploy --url "$RPC_URL" \
  --class-hash "$CLASS_HASH_UM" \
  --constructor-calldata \
    "$AIC_ADDR" "$OWNER_ADDR" \
    $FREE_QUOTA $PRICE_LO $PRICE_HI \
    $EPOCH_SECONDS "$OWNER_ADDR")

echo "$OUT"

UM_ADDR=$(echo "$OUT" | awk '/Contract address:/ {print $3}')

echo
echo "================ RESULT ================"
echo "UM_ADDR : $UM_ADDR"
echo "AIC_ADDR: $AIC_ADDR"
echo "Explorer: https://sepolia.starkscan.co/contract/$UM_ADDR"
echo "========================================"
