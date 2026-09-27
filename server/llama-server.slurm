#!/bin/bash -l
#SBATCH --partition=kshdnormal
#SBATCH --gres=dcu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=27gb
#SBATCH --time=08:00:00
#SBATCH --job-name=scnet-eva-server

set -euo pipefail

export LC_ALL=C
export LANG=C
export LANGUAGE=C

module purge
module load compiler/gcc/11.2.0
module load compiler/dtk/26.04

app_dir="${SCNET_SERVER_APP_DIR:-$HOME/.scnet-aichat}"
binary="${SCNET_LLAMA_SERVER:-$HOME/eva-k100/llama.cpp-b5046/build-gfx906/bin/llama-server}"
model="${SCNET_SERVER_MODEL:-$HOME/models/EVA-Qwen2.5-14B-v0.2-GGUF-Q4_0/EVA-Qwen2.5-14B-v0.2-Q4_0.gguf}"
port="${SCNET_SERVER_PORT:-18080}"
api_key="${SCNET_SERVER_API_KEY:-}"

mkdir -p "$app_dir/server"
[[ -x "$binary" ]] || { echo "missing llama-server: $binary" >&2; exit 69; }
[[ -f "$model" ]] || { echo "missing model: $model" >&2; exit 66; }

node="$(hostname)"
printf '%s\n' "$SLURM_JOB_ID" > "$app_dir/server/job_id"
printf '%s\n' "$node" > "$app_dir/server/node"
printf '%s\n' "$port" > "$app_dir/server/port"
printf '%s\n' "$model" > "$app_dir/server/model"
date '+%Y-%m-%dT%H:%M:%S%z' > "$app_dir/server/started_at"

cleanup() {
  rc=$?
  printf '%s\n' "$rc" > "$app_dir/server/exit_code"
  date '+%Y-%m-%dT%H:%M:%S%z' > "$app_dir/server/finished_at"
}
trap cleanup EXIT

args=(
  --model "$model"
  --host 0.0.0.0
  --port "$port"
  --ctx-size 4096
  --batch-size 256
  --ubatch-size 256
  --parallel 1
  --gpu-layers 99
  --jinja
  --metrics
)
if [[ -n "$api_key" ]]; then
  args+=(--api-key "$api_key")
fi

exec "$binary" "${args[@]}"
