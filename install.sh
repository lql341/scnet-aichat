#!/usr/bin/env bash

# Install scnet-aichat for the current user or into a chosen prefix.
# Bash 3.2 compatible: macOS, Ubuntu, Debian.

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${SCNET_AICHAT_PREFIX:-${HOME}/.local}"
INIT_CONFIG=1
REMOTE_INSTALL=0
RUN_TESTS=0

usage() {
  cat <<'EOF'
Usage:
  ./install.sh                         install for the current user
  ./install.sh --remote-install        install local files and remote Slurm workers
  ./install.sh --check                 install and run local tests
  ./install.sh --prefix /usr/local     install system-wide (may need sudo)
  ./install.sh --no-init-config        do not create a config file

Environment:
  SCNET_AICHAT_PREFIX
  SCNET_AICHAT_CONFIG
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix)
      [[ $# -ge 2 ]] || { echo "--prefix needs a value" >&2; exit 2; }
      PREFIX="$2"
      shift 2
      ;;
    --remote-install)
      REMOTE_INSTALL=1
      shift
      ;;
    --check)
      RUN_TESTS=1
      shift
      ;;
    --no-init-config)
      INIT_CONFIG=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

for tool in bash install cp; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "missing local command: $tool" >&2
    exit 1
  }
done

BIN_DIR="${PREFIX}/bin"
SHARE_DIR="${PREFIX}/share/scnet-aichat"
CONFIG_DIR="${HOME}/.config/scnet-aichat"
CONFIG_FILE="${SCNET_AICHAT_CONFIG:-${CONFIG_DIR}/config}"

mkdir -p \
  "$BIN_DIR" "$SHARE_DIR/worker" "$SHARE_DIR/server" \
  "$SHARE_DIR/scripts" "$CONFIG_DIR"
install -m 755 "$SCRIPT_DIR/scnet-aichat" "$BIN_DIR/scnet-aichat"
install -m 755 "$SCRIPT_DIR/worker/scnet-aichat-worker.slurm" \
  "$SHARE_DIR/worker/scnet-aichat-worker.slurm"
install -m 755 "$SCRIPT_DIR/server/llama-server.slurm" \
  "$SHARE_DIR/server/llama-server.slurm"
install -m 755 "$SCRIPT_DIR/server/build-server.sh" \
  "$SHARE_DIR/server/build-server.sh"
install -m 755 "$SCRIPT_DIR/server/start-server.sh" \
  "$SHARE_DIR/server/start-server.sh"
install -m 755 "$SCRIPT_DIR/scripts/scnet-openapi.py" \
  "$SHARE_DIR/scripts/scnet-openapi.py"
install -m 644 "$SCRIPT_DIR/config.example" "$SHARE_DIR/config.example"

if [[ "$INIT_CONFIG" == "1" && ! -e "$CONFIG_FILE" ]]; then
  cp "$SCRIPT_DIR/config.example" "$CONFIG_FILE"
  chmod 600 "$CONFIG_FILE" 2>/dev/null || true
  echo "Created config: $CONFIG_FILE"
fi

if [[ "$RUN_TESTS" == "1" ]]; then
  "$SCRIPT_DIR/tests/test.sh"
fi

echo "Installed: $BIN_DIR/scnet-aichat"
case ":${PATH}:" in
  *":${BIN_DIR}:"*) ;;
  *) echo "Add to PATH: export PATH=\"${BIN_DIR}:\$PATH\"" ;;
esac

if [[ "$REMOTE_INSTALL" == "1" ]]; then
  "$BIN_DIR/scnet-aichat" install
  "$BIN_DIR/scnet-aichat" doctor
fi
