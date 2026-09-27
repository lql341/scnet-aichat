#!/usr/bin/env bash

set -euo pipefail

: "${SCNET_LLAMA_SERVER:=/opt/scnet-aichat/bin/llama-server}"
: "${SCNET_MODEL_PATH:=/models/EVA-Qwen2.5-14B-v0.2-Q4_0.gguf}"
: "${SCNET_PORT:=8080}"

exec "$SCNET_LLAMA_SERVER" \
  --model "$SCNET_MODEL_PATH" \
  --host 0.0.0.0 \
  --port "$SCNET_PORT" \
  --ctx-size "${SCNET_CTX_SIZE:-4096}" \
  --batch-size "${SCNET_BATCH_SIZE:-256}" \
  --ubatch-size "${SCNET_UBATCH_SIZE:-256}" \
  --parallel "${SCNET_PARALLEL:-1}" \
  --gpu-layers 99 \
  --jinja \
  --metrics
