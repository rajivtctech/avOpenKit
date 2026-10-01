#!/usr/bin/env bash
# Build the Linux download on this machine, in an Ubuntu 22.04 container, so that the file runs
# on 22.04 and newer - the same compatibility as the build GitHub makes.
#   packaging/build_linux_container.sh        -> dist/avOpenKit-linux-x86_64
#
# Needs podman. The first run builds the image (about 1 GB, needs the network once); after that
# a build uses no network. Inside the container it runs the tests under 22.04's Python, builds,
# and runs the packaged program's self-test; then the result is self-tested again out here, on
# this machine's own system and FFmpeg, which is the check that it really is portable.
#   AVOPENKIT_SKIP_TESTS=1   build and self-test only
#   AVOPENKIT_REBUILD_IMAGE=1   rebuild the image (to pick up newer packages)
set -euo pipefail
cd "$(dirname "$0")/.."
IMAGE=avopenkit-build:22.04
if [ "${AVOPENKIT_REBUILD_IMAGE:-0}" = "1" ] || ! podman image exists "$IMAGE"; then
    echo "==> building the image (first time only)"
    podman build -t "$IMAGE" -f packaging/Containerfile packaging
fi
mkdir -p dist
git ls-files -co --exclude-standard | grep -v -E '^(docs/.*\.(pdf|odt)|dist/|build/)' > .container-files
trap 'rm -f .container-files' EXIT
echo "==> building in the container"
podman run --rm --network none -e AVOPENKIT_SKIP_TESTS="${AVOPENKIT_SKIP_TESTS:-0}" \
    -v "$PWD":/src:ro -v "$PWD/dist":/out "$IMAGE" bash /src/packaging/container_build.sh
ls -la dist/avOpenKit-linux-x86_64
echo "==> self-test on this machine ($(. /etc/os-release && echo "$PRETTY_NAME"))"
clip=$(mktemp --suffix=.mp4); trap 'rm -f .container-files "$clip"' EXIT
ffmpeg -v error -y -f lavfi -i testsrc2=size=640x360:rate=30:duration=4 \
    -f lavfi -i sine=frequency=440:duration=4 -c:v libx264 -pix_fmt yuv420p -c:a aac "$clip"
(cd /tmp && "$OLDPWD/dist/avOpenKit-linux-x86_64" --self-test "$clip")
