#!/bin/bash
# Runs INSIDE the build container (see build_linux_container.sh). /src is the repository,
# read-only; /out receives the result.
set -euo pipefail
mkdir -p /work && cd /src
# A private copy: the build writes build/ and dist/, and must not touch the repository.
git_files=$(cat /src/.container-files)
echo "$git_files" | tr '\n' '\0' | xargs -0 cp --parents -t /work
cd /work
python3 --version; ffmpeg -version | head -1
if [ "${AVOPENKIT_SKIP_TESTS:-0}" != "1" ]; then
    python -m pytest -q -p no:cacheprovider
fi
pyinstaller --clean --noconfirm avopenkit.spec > /out/linux-build.log 2>&1 \
    || { echo "PyInstaller failed:"; tail -5 /out/linux-build.log; exit 1; }
ffmpeg -v error -y -f lavfi -i testsrc2=size=640x360:rate=30:duration=4 \
    -f lavfi -i sine=frequency=440:duration=4 -c:v libx264 -pix_fmt yuv420p -c:a aac /tmp/clip.mp4
./dist/avOpenKit --version
./dist/avOpenKit --self-test /tmp/clip.mp4
cp dist/avOpenKit /out/avOpenKit-linux-x86_64
