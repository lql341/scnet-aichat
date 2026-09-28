#!/usr/bin/env bash

set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLIENT="${ROOT}/scnet-aichat"
WORKER="${ROOT}/worker/scnet-aichat-worker.slurm"
SERVER_JOB="${ROOT}/server/llama-server.slurm"
SERVER_BUILD="${ROOT}/server/build-server.sh"
SERVER_START="${ROOT}/server/start-server.sh"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

pass() {
  printf 'PASS: %s\n' "$*"
}

/bin/bash -n "$CLIENT" "$WORKER" "$SERVER_JOB" "$SERVER_BUILD" "$SERVER_START" ||
  fail "Bash syntax"
pass "Bash syntax"

if grep -nE 'declare[[:space:]]+-A|mapfile|readarray|date[^#]*%N|\$\{[^}]*,,|\$\{[^}]*\^\^' \
  "$CLIENT" "$WORKER" >/dev/null 2>&1; then
  fail "Bash 4+ syntax detected"
fi
pass "Bash 3.2 compatibility scan"

"$CLIENT" --help >/dev/null || fail "help command"
pass "help command"

dry14="$(SCNET_REMOTE_HOME=/remote/home "$CLIENT" --dry-run --model 14b ask test)"
printf '%s\n' "$dry14" | grep -q 'resources=dcu:1 cpu:8 mem:27gb' ||
  fail "14B resource mapping"
pass "14B resource mapping"

dry32="$(SCNET_REMOTE_HOME=/remote/home "$CLIENT" --dry-run --model 32b ask test)"
printf '%s\n' "$dry32" | grep -q 'resources=dcu:4 cpu:32 mem:110gb' ||
  fail "32B resource mapping"
pass "32B resource mapping"

dry_server="$(SCNET_REMOTE_HOME=/remote/home "$CLIENT" --dry-run --mode server --model 14b ask test)"
printf '%s\n' "$dry_server" | grep -q 'persistent_model=14b' ||
  fail "persistent server mode"
pass "persistent server mode"

set +e
"$CLIENT" --model 72b doctor >/dev/null 2>&1
bad_model=$?
"$CLIENT" --max-tokens 0 --dry-run ask test >/dev/null 2>&1
bad_tokens=$?
set -e
[[ $bad_model -ne 0 && $bad_tokens -ne 0 ]] || fail "invalid input rejection"
pass "invalid input rejection"

case "${SCNET_AICHAT_REMOTE_TESTS:-0}" in
  1)
    "$CLIENT" doctor >/dev/null || fail "remote doctor"
    pass "remote doctor"
    ;;
  *) printf 'SKIP: remote doctor (set SCNET_AICHAT_REMOTE_TESTS=1)\n' ;;
esac

printf 'All tests passed.\n'
