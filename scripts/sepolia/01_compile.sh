#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

require_cmd scarb
require_cmd jq

cd "$ROOT_DIR"

echo "==> Compilando contratos con scarb --release build"
scarb --release build

ARTIFACT_SOURCE="target/release/tokenxllm.starknet_artifacts.json"
ARTIFACT_TARGET="target/release/starknet_artifacts.json"

if [ -f "$ARTIFACT_SOURCE" ]; then
  cp -f "$ARTIFACT_SOURCE" "$ARTIFACT_TARGET"
fi

echo "==> Contratos disponibles:"
echo "==> Contratos disponibles:"
if jq -e '.contracts | type == "array"' "$ARTIFACT_TARGET" > /dev/null; then
  # Formato viejo: array de contratos con campo .name
  jq -r '.contracts[] | (.name // .contract_name // .id)' "$ARTIFACT_TARGET"
else
  # Formato nuevo: objeto cuyas keys son los nombres
  jq -r '.contracts | keys[]' "$ARTIFACT_TARGET"
fi
