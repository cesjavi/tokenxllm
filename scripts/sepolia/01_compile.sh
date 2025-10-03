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
jq -r '.contracts[] | .name' "$ARTIFACT_TARGET"
