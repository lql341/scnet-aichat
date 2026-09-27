#!/usr/bin/env bash

set -euo pipefail

export LC_ALL=C
export LANG=C
export LANGUAGE=C

module purge
module load "${SCNET_GCC_MODULE:-compiler/gcc/11.2.0}"
module load "${SCNET_CMAKE_MODULE:-compiler/cmake/3.25.0}"
module load "${SCNET_MAKE_MODULE:-compiler/make/4.4}"
module load "${SCNET_DTK_MODULE:-compiler/dtk/26.04}"

src="${SCNET_LLAMA_SRC:-$HOME/eva-k100/llama.cpp-b5046}"
build="${SCNET_LLAMA_BUILD:-$src/build-gfx906}"
export CC="${CC:-$(command -v gcc)}"
export CXX="${CXX:-$(command -v g++)}"

cmake -S "$src" -B "$build" \
  -DGGML_HIP=ON \
  -DAMDGPU_TARGETS=gfx906 \
  -DCMAKE_HIP_ARCHITECTURES=gfx906 \
  -DCMAKE_HIP_FLAGS=--gcc-toolchain=/public/software/compiler/gcc/11.2.0 \
  -DCMAKE_PREFIX_PATH=/public/software/compiler/rocm/dtk-26.04/dcc/comgr \
  -Damd_comgr_DIR=/public/software/compiler/rocm/dtk-26.04/dcc/comgr/lib64/cmake/amd_comgr \
  "-DCMAKE_TRY_COMPILE_PLATFORM_VARIABLES=CMAKE_PREFIX_PATH;amd_comgr_DIR" \
  -DGGML_NATIVE=OFF \
  -DGGML_CCACHE=OFF \
  -DGGML_HIP_NO_VMM=ON \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_SERVER=ON \
  -DLLAMA_CURL=OFF \
  -DBUILD_SHARED_LIBS=OFF

cmake --build "$build" --target llama-server -j"${SCNET_BUILD_JOBS:-8}"
stat -c '%s %n' "$build/bin/llama-server"
