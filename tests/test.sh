#!/usr/bin/env bash

set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLIENT="${ROOT}/scnet-aichat"
WORKER="${ROOT}/worker/scnet-aichat-worker.slurm"
SERVER_JOB="${ROOT}/server/llama-server.slurm"
SERVER_BUILD="${ROOT}/server/build-server.sh"
SERVER_START="${ROOT}/server/start-server.sh"
OPENAPI_HELPER="${ROOT}/scripts/scnet-openapi.py"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

pass() {
  printf 'PASS: %s\n' "$*"
}

TMP_INSTALL="$(mktemp -d "${TMPDIR:-/tmp}/scnet-aichat-test.XXXXXX")"
trap 'rm -rf "$TMP_INSTALL"' EXIT

/bin/bash -n "$CLIENT" "$WORKER" "$SERVER_JOB" "$SERVER_BUILD" "$SERVER_START" ||
  fail "Bash syntax"
pass "Bash syntax"

python3 -c 'import pathlib,sys; compile(pathlib.Path(sys.argv[1]).read_text(), sys.argv[1], "exec")' \
  "$OPENAPI_HELPER" ||
  fail "OpenAPI helper syntax"
PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT/tests/test_openapi.py" ||
  fail "OpenAPI helper tests"
pass "OpenAPI helper"

if grep -nE 'declare[[:space:]]+-A|mapfile|readarray|date[^#]*%N|\$\{[^}]*,,|\$\{[^}]*\^\^' \
  "$CLIENT" "$WORKER" >/dev/null 2>&1; then
  fail "Bash 4+ syntax detected"
fi
pass "Bash 3.2 compatibility scan"

"$CLIENT" --help >/dev/null || fail "help command"
pass "help command"

malicious_config="$TMP_INSTALL/malicious-config"
malicious_marker="$TMP_INSTALL/config-was-executed"
printf 'SCNET_PROFILE=$(touch %s)\n' "$malicious_marker" > "$malicious_config"
SCNET_AICHAT_CONFIG="$malicious_config" "$CLIENT" --help >/dev/null ||
  fail "safe config parser"
[[ ! -e "$malicious_marker" ]] || fail "config executed shell code"
printf 'SCNET_OPENAPI_SECRET_KEY=must-not-be-here\n' > "$malicious_config"
set +e
SCNET_AICHAT_CONFIG="$malicious_config" "$CLIENT" --help >/dev/null 2>&1
secret_config=$?
set -e
[[ $secret_config -ne 0 ]] || fail "credential accepted in config"
printf 'SCNET_OPENAPI_REGION_ID=11250\n' > "$malicious_config"
set +e
SCNET_AICHAT_CONFIG="$malicious_config" "$CLIENT" --help >/dev/null 2>&1
region_config=$?
set -e
[[ $region_config -ne 0 ]] || fail "setup-managed region accepted in config"
pass "safe config parser"

"$ROOT/install.sh" --prefix "$TMP_INSTALL/prefix" --no-init-config ||
  fail "user-prefix installer"
"$TMP_INSTALL/prefix/bin/scnet-aichat" --help >/dev/null ||
  fail "installed client"
[[ -f "$TMP_INSTALL/prefix/share/scnet-aichat/worker/scnet-aichat-worker.slurm" ]] ||
  fail "installed worker layout"
[[ -f "$TMP_INSTALL/prefix/share/scnet-aichat/scripts/scnet-openapi.py" ]] ||
  fail "installed OpenAPI helper"
pass "user-prefix installer"

dry14="$(SCNET_REMOTE_HOME=/remote/home "$CLIENT" --backend ssh --dry-run --model 14b ask test)"
printf '%s\n' "$dry14" | grep -q 'resources=dcu:1 cpu:8 mem:27gb' ||
  fail "14B resource mapping"
pass "14B resource mapping"

dry32="$(SCNET_REMOTE_HOME=/remote/home "$CLIENT" --backend ssh --dry-run --model 32b ask test)"
printf '%s\n' "$dry32" | grep -q 'resources=dcu:4 cpu:32 mem:110gb' ||
  fail "32B resource mapping"
pass "32B resource mapping"

dry_server="$(SCNET_REMOTE_HOME=/remote/home "$CLIENT" --backend ssh --dry-run --mode server --model 14b ask test)"
printf '%s\n' "$dry_server" | grep -q 'persistent_model=14b' ||
  fail "persistent server mode"
pass "persistent server mode"

dry_openapi="$(SCNET_REMOTE_HOME=/remote/home \
  "$TMP_INSTALL/prefix/bin/scnet-aichat" \
  --backend openapi --dry-run --model 14b ask test)"
printf '%s\n' "$dry_openapi" | grep -q 'backend=openapi' ||
  fail "OpenAPI dry-run"
if printf '%s\n' "$dry_openapi" | grep -q '/remote/home'; then
  fail "OpenAPI dry-run path redaction"
fi
pass "OpenAPI dry-run and path redaction"

SCNET_REMOTE_HOME=/remote/home "$CLIENT" --backend ssh --dry-run --preset eva-rp ask test >/dev/null ||
  fail "EVA roleplay preset"
pass "EVA roleplay preset"

set +e
"$CLIENT" --model 72b doctor >/dev/null 2>&1
bad_model=$?
"$CLIENT" --backend ssh --max-tokens 0 --dry-run ask test >/dev/null 2>&1
bad_tokens=$?
SCNET_14B_MEM='27gb;invalid' "$CLIENT" --backend ssh --dry-run ask test >/dev/null 2>&1
bad_memory=$?
"$CLIENT" --backend invalid --dry-run ask test >/dev/null 2>&1
bad_backend=$?
set -e
[[ $bad_model -ne 0 && $bad_tokens -ne 0 && $bad_memory -ne 0 && $bad_backend -ne 0 ]] ||
  fail "invalid input rejection"
pass "invalid input rejection"

case "${SCNET_AICHAT_REMOTE_TESTS:-0}" in
  1)
    "$CLIENT" doctor >/dev/null || fail "remote doctor"
    pass "remote doctor"
    ;;
  *) printf 'SKIP: remote doctor (set SCNET_AICHAT_REMOTE_TESTS=1)\n' ;;
esac

printf 'All tests passed.\n'
