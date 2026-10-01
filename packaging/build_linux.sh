#!/usr/bin/env bash
# Build the single-file Linux program: dist/avOpenKit
#   packaging/build_linux.sh
# Uses its own environment (.venv-build) so build tools stay out of the development one.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv-build/bin/pyinstaller ]; then
    python3 -m venv .venv-build
    .venv-build/bin/pip install -q --disable-pip-version-check -e . pyinstaller
fi
.venv-build/bin/pyinstaller --clean --noconfirm avopenkit.spec
ls -la dist/avOpenKit
dist/avOpenKit --self-test
