#!/usr/bin/env bash

set -eu

PREFIX="${SCNET_AICHAT_PREFIX:-${HOME}/.local}"
CONFIG_FILE="${SCNET_AICHAT_CONFIG:-${HOME}/.config/scnet-aichat/config}"

rm -f "${PREFIX}/bin/scnet-aichat"
rm -rf "${PREFIX}/share/scnet-aichat"
echo "Removed local installation from ${PREFIX}"
echo "Preserved config: ${CONFIG_FILE}"
echo "Preserved remote workers and models. Remove them manually only if intended:"
echo "  scnet-aichat install does not delete remote data."
