#!/usr/bin/env bash
# Publish a release on GitHub from the downloads built on this machine.
#   packaging/build_linux_container.sh && packaging/build_windows_vm.sh
#   packaging/release_local.sh
# The release is v<version>, the version in avopenkit/__init__.py. Everything must be committed
# and pushed first: the tag is made on the commit that GitHub's main branch points to.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' avopenkit/__init__.py)
TAG=v$VERSION
FFMPEG_VERSION=9.0.2          # the FFmpeg in the Windows download: packaging/fetch_ffmpeg_windows.py
FFMPEG_SOURCE_COMMIT=946fcce07b6dcd0331c8cc609192aeff5e1924f8
CACHE=${XDG_CACHE_HOME:-$HOME/.cache}/avopenkit-build
LINUX=dist/avOpenKit-linux-x86_64
WINDOWS=dist/avOpenKit-windows-x64.zip

[ -z "$(git status --porcelain)" ] || { echo "there are uncommitted changes; commit them first" >&2; exit 1; }
git fetch -q origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "this commit is not what GitHub's main has; push first" >&2; exit 1; }
gh release view "$TAG" >/dev/null 2>&1 && { echo "release $TAG already exists" >&2; exit 1; }

echo "==> checking the downloads are version $VERSION"
[ -x "$LINUX" ] && [ -f "$WINDOWS" ] || { echo "build both downloads first" >&2; exit 1; }
[ "$("$LINUX" --version)" = "avOpenKit $VERSION" ] || { echo "$LINUX is not version $VERSION" >&2; exit 1; }
grep -q "^avOpenKit $VERSION;" "${AVOPENKIT_VM:-$HOME/vmware/Windows11-Pro}/share/build/selftest.txt" \
    || { echo "the last Windows build was not version $VERSION" >&2; exit 1; }
cmp -s "$WINDOWS" "${AVOPENKIT_VM:-$HOME/vmware/Windows11-Pro}/share/build/avOpenKit-windows-x64.zip" \
    || { echo "$WINDOWS is not the file the last Windows build made" >&2; exit 1; }

echo "==> collecting the release files"
OUT=$(mktemp -d); trap 'rm -rf "$OUT"' EXIT
SOURCE=$CACHE/ffmpeg-$FFMPEG_VERSION-source.tar.gz
mkdir -p "$CACHE"
[ -f "$SOURCE" ] || curl -sSL -o "$SOURCE" "https://github.com/FFmpeg/FFmpeg/archive/$FFMPEG_SOURCE_COMMIT.tar.gz"
FIRST=$(tar -tzf "$SOURCE" 2>/dev/null | head -1 || true)   # head closes the pipe early
[ "${FIRST%%/*}" = "FFmpeg-$FFMPEG_SOURCE_COMMIT" ] || { echo "$SOURCE is not the FFmpeg source expected" >&2; exit 1; }
cp "$LINUX" "$WINDOWS" "$SOURCE" docs/avOpenKit-User-Guide.pdf docs/avOpenKit-User-Guide-A5.pdf \
   packaging/THIRD-PARTY-NOTICES.md "$OUT/"
(cd "$OUT" && sha256sum * > SHA256SUMS.txt && cat SHA256SUMS.txt)

echo "==> publishing $TAG"
gh release create "$TAG" "$OUT"/* --target "$(git rev-parse HEAD)" --prerelease \
    --title "$TAG" --notes-file packaging/RELEASE_NOTES.md
gh release view "$TAG" --json url,assets --jq '.url, (.assets[] | "\(.name)  \(.size)")'
