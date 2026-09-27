#!/bin/bash -l

set -euo pipefail

export LC_ALL=C
export LANG=C
export LANGUAGE=C

gcc_module="${SCNET_GCC_MODULE:-compiler/gcc/11.2.0}"
dtk_module="${SCNET_DTK_MODULE:-compiler/dtk/26.04}"

case "$gcc_module:$dtk_module" in
  *[!A-Za-z0-9_./:+-]*)
    echo "invalid module name" >&2
    exit 64
    ;;
esac

module purge
module load "$gcc_module"
module load "$dtk_module"

request_dir="${EVA_REQUEST_DIR:-}"
model_key="${EVA_MODEL_KEY:-}"

case "$request_dir" in
  /*) ;;
  *) echo "EVA_REQUEST_DIR must be absolute" >&2; exit 64 ;;
esac
case "$request_dir" in
  *[!A-Za-z0-9_./-]*) echo "unsafe EVA_REQUEST_DIR" >&2; exit 64 ;;
esac
case "$model_key" in
  14b|32b) ;;
  *) echo "unsupported model: $model_key" >&2; exit 64 ;;
esac

prompt_file="${request_dir}/prompt.txt"
system_file="${request_dir}/system.txt"
tokens_file="${request_dir}/max_tokens"
binary_file="${request_dir}/llama_cli"
model_file="${request_dir}/model_path"

for required_file in "$prompt_file" "$tokens_file" "$binary_file" "$model_file"; do
  [[ -f "$required_file" ]] || {
    echo "missing request file: $required_file" >&2
    exit 66
  }
done

system_prompt="You are a helpful assistant. Answer coherently and directly."
if [[ -s "$system_file" ]]; then
  system_prompt="$(cat "$system_file")"
fi

max_tokens="$(tr -d '[:space:]' < "$tokens_file")"
case "$max_tokens" in
  ""|*[!0-9]*) echo "invalid max_tokens" >&2; exit 64 ;;
esac
if (( max_tokens < 1 || max_tokens > 4096 )); then
  echo "max_tokens must be between 1 and 4096" >&2
  exit 64
fi

binary="$(cat "$binary_file")"
model="$(cat "$model_file")"
for remote_path in "$binary" "$model"; do
  case "$remote_path" in
    /*) ;;
    *) echo "runtime paths must be absolute" >&2; exit 64 ;;
  esac
  case "$remote_path" in
    *[!A-Za-z0-9_./+-]*) echo "unsafe runtime path" >&2; exit 64 ;;
  esac
done

[[ -x "$binary" ]] || {
  echo "missing executable: $binary" >&2
  exit 69
}
[[ -f "$model" ]] || {
  echo "missing model: $model" >&2
  exit 66
}

visible_devices="${CUDA_VISIBLE_DEVICES:-}"
if [[ -z "$visible_devices" ]]; then
  if [[ "$model_key" == "32b" ]]; then
    visible_devices="0,1,2,3"
  else
    visible_devices="0"
  fi
fi
export HIP_VISIBLE_DEVICES="$visible_devices"
export ROCR_VISIBLE_DEVICES="$visible_devices"

threads="${SLURM_CPUS_PER_TASK:-8}"
prompt="$(cat "$prompt_file")"

on_exit() {
  rc=$?
  printf '%s\n' "$rc" > "${request_dir}/exit_code"
  date '+%Y-%m-%dT%H:%M:%S%z' > "${request_dir}/finished_at"
}
trap on_exit EXIT

date '+%Y-%m-%dT%H:%M:%S%z' > "${request_dir}/started_at"
printf '%s\n' "$model_key" > "${request_dir}/model"
printf '%s\n' "$SLURM_JOB_ID" > "${request_dir}/job_id"

echo "=== SCNET_AICHAT_META ==="
printf 'model=%s\nmax_tokens=%s\nthreads=%s\nvisible_devices=%s\n' \
  "$model_key" "$max_tokens" "$threads" "$visible_devices"
echo "=== SCNET_AICHAT_ANSWER_BEGIN ==="
"$binary" \
  --model "$model" \
  --gpu-layers 99 \
  --ctx-size 4096 \
  --batch-size 256 \
  --ubatch-size 256 \
  --threads "$threads" \
  --n-predict "$max_tokens" \
  --temp 0.7 \
  --top-p 0.9 \
  --min-p 0.05 \
  --repeat-penalty 1.03 \
  --seed 20260927 \
  --no-warmup \
  --no-display-prompt \
  --jinja \
  --single-turn \
  --system-prompt "$system_prompt" \
  --prompt "$prompt" |
  tee "${request_dir}/answer.txt"
echo
echo "=== SCNET_AICHAT_ANSWER_END ==="
