CLASS_HASH_UM=0x02f0138bd302692bb1c1b01561f72f6df01a0aa09c1470a132f6837b0a26fc97

ACC_FILE="$HOME/.starknet_accounts/starknet_open_zeppelin_accounts.json"
ACCOUNT="dev"
RPC_URL="https://starknet-sepolia.public.blastapi.io/rpc/v0_9"
AIC_ADDR="0x06ddaf09636ceb526485c55b93c48c70f2a1728ad223743aaf08c21362ae7d9e"
OWNER_ADDR="0x522570db5197d282febafea3538ff2deacfaf49ec85a86e30bbe45af6f7c90"

# por las dudas, esperá unos segunditos
sleep 10

sncast --account "$ACCOUNT" --accounts-file "$ACC_FILE" \
  deploy --url "$RPC_URL" \
  --class-hash "$CLASS_HASH_UM" \
  --constructor-calldata \
    "$AIC_ADDR" "$OWNER_ADDR" \
    3000 10000000000000000 0 \
    86400 "$OWNER_ADDR"

