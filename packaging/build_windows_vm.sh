#!/usr/bin/env bash
# Build the Windows download on this machine, inside the Windows 11 virtual machine.
#   packaging/build_windows_vm.sh        -> dist/avOpenKit-windows-x64.zip
#
# PyInstaller cannot build a Windows program from Linux, so the build runs in real Windows:
# the VM at ~/vmware/Windows11-Pro (VMware Workstation). Nothing outside this machine is used
# once the downloads below are cached. What it does:
#   1. stages the source, the FFmpeg to bundle, and the Python packages (as Windows wheels)
#      in the folder the VM shares with this machine;
#   2. starts the VM without a window and runs b.cmd in it - by typing Win+R, "d:\b", Enter,
#      because the VM's account has no password and so cannot be scripted the usual way;
#   3. in the VM: copy the source to C:\avbuild, install the packages without the internet,
#      run PyInstaller, run the packaged program's --self-test, zip the result;
#   4. collects the zip, the build log and the self-test report, and shuts the VM down.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
VM=${AVOPENKIT_VM:-$HOME/vmware/Windows11-Pro}
VMX=$VM/Windows11-Pro.vmx
STAGE=$VM/share/build
CACHE=${XDG_CACHE_HOME:-$HOME/.cache}/avopenkit-build
PYVER=3.14.8
[ -f "$VMX" ] || { echo "no virtual machine at $VMX" >&2; exit 1; }
pgrep -x vmware-vmx >/dev/null && { echo "a virtual machine is already running; shut it down first" >&2; exit 1; }

echo "==> staging source, FFmpeg and packages"
rm -rf "$STAGE"; mkdir -p "$STAGE/src" "$CACHE/wheels"
git ls-files -co --exclude-standard -z | grep -zv -E '^(docs/.*\.(pdf|odt)|dist/|build/)' \
    | xargs -0 cp --parents -t "$STAGE/src"
[ -f packaging/ffmpeg-win/ffmpeg.exe ] || .venv/bin/python packaging/fetch_ffmpeg_windows.py
mkdir -p "$STAGE/src/packaging/ffmpeg-win" && cp packaging/ffmpeg-win/* "$STAGE/src/packaging/ffmpeg-win/"
.venv/bin/pip download -q --disable-pip-version-check --platform win_amd64 --python-version "${PYVER%.*}" \
    --only-binary=:all: -d "$CACHE/wheels" pyinstaller pefile pywin32-ctypes PyQt6
[ -f "$CACHE/python-$PYVER-amd64.exe" ] || curl -sSL -o "$CACHE/python-$PYVER-amd64.exe" \
    "https://www.python.org/ftp/python/$PYVER/python-$PYVER-amd64.exe"
cp -r "$CACHE/wheels" "$STAGE/wheels"; cp "$CACHE/python-$PYVER-amd64.exe" "$STAGE/python-installer.exe"

echo "==> build disc"
ISO_DIR=$(mktemp -d); trap 'rm -rf "$ISO_DIR"' EXIT
cat > "$ISO_DIR/b.cmd" <<'CMD'
@echo off
set S=\\vmware-host\Shared Folders\share\build
set PY=C:\avbuild-python\python.exe
rmdir /s /q C:\avbuild 2>nul
mkdir C:\avbuild
set L=C:\avbuild\build.log
echo build started %date% %time% > %L%
rem Python: the build's own copy, else one already in the VM (the installer will not put a
rem second copy of the same version somewhere else), else install it now.
if exist %PY% goto havepy
if exist C:\avtrial\py\python.exe set PY=C:\avtrial\py\python.exe
if exist %PY% goto havepy
copy /y "%S%\python-installer.exe" C:\avbuild\python-installer.exe >nul
start /wait "" C:\avbuild\python-installer.exe /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 TargetDir=C:\avbuild-python
echo python installer exit %errorlevel% >> %L%
if exist %PY% goto havepy
echo Python could not be installed in the virtual machine >> %L%
goto finish
:havepy
echo using %PY% >> %L%
%PY% --version >> %L% 2>&1
xcopy "%S%\src" C:\avbuild\src\ /e /i /q /y >> %L% 2>&1
%PY% -m pip install --no-index --find-links "%S%\wheels" --upgrade pyinstaller PyQt6 >> %L% 2>&1
cd /d C:\avbuild\src
%PY% -m PyInstaller --clean --noconfirm avopenkit.spec >> %L% 2>&1
echo pyinstaller exit %errorlevel% >> %L%
packaging\ffmpeg-win\ffmpeg.exe -v error -y -f lavfi -i testsrc2=size=640x360:rate=30:duration=4 -f lavfi -i sine=frequency=440:duration=4 -c:v libx264 -pix_fmt yuv420p -c:a aac C:\avbuild\clip.mp4 >> %L% 2>&1
if exist dist\avOpenKit\avOpenKit.exe goto built
echo the build produced no program >> %L%
goto finish
:built
set AVOPENKIT_SELFTEST_REPORT=C:\avbuild\selftest.txt
start /wait "" dist\avOpenKit\avOpenKit.exe --self-test C:\avbuild\clip.mp4
echo exit code %errorlevel% >> C:\avbuild\selftest.txt
powershell -NoProfile -Command "Compress-Archive -Path C:\avbuild\src\dist\avOpenKit -DestinationPath C:\avbuild\avOpenKit-windows-x64.zip -Force" >> %L% 2>&1
copy /y C:\avbuild\avOpenKit-windows-x64.zip "%S%\" >nul
copy /y C:\avbuild\selftest.txt "%S%\" >nul
:finish
echo build finished %date% %time% >> %L%
copy /y %L% "%S%\" >nul
echo done > "%S%\done.txt"
CMD
sed -i 's/$/\r/' "$ISO_DIR/b.cmd"
genisoimage -quiet -J -r -V AVBUILD -o "$VM/winbuild.iso" "$ISO_DIR"

set_cd () {   # image path, connected at start (TRUE/FALSE)
    python3 - "$VMX" "$1" "$2" <<'PY'
import sys
x, iso, connected = sys.argv[1:4]
lines = [l for l in open(x).read().split("\n")
         if l.strip() and not l.startswith(("sata0:1.fileName", "sata0:1.startConnected"))]
lines += [f'sata0:1.fileName = "{iso}"', f'sata0:1.startConnected = "{connected}"']
open(x, "w").write("\n".join(lines) + "\n")
PY
}
key () { timeout 5 vmcli "$VMX" MKS sendKeyEvent $(( ($1 << 16) | 7 )) "${2:-0}" >/dev/null 2>&1 || true; sleep 0.4; }

echo "==> starting the virtual machine"
set_cd "$VM/winbuild.iso" TRUE
( timeout 120 vmrun -T ws start "$VMX" nogui >/dev/null 2>&1 & )
sleep "${AVOPENKIT_VM_BOOT_SECONDS:-80}"
key 0x2c; sleep 1; key 0x29; sleep 1     # wake the screen, Esc
key 0x15 8; sleep 3                       # Win+R
key 0x07; key 0x33 2; key 0x31; key 0x05  # d : \ b
sleep 1; key 0x28                         # Enter

echo "==> building in Windows (several minutes)"
for i in $(seq 1 180); do [ -f "$STAGE/done.txt" ] && break; sleep 10; done
echo "==> shutting the virtual machine down"
timeout 150 vmrun -T ws stop "$VMX" soft >/dev/null 2>&1 || true
for i in $(seq 1 40); do pgrep -x vmware-vmx >/dev/null || break; sleep 3; done
set_cd "$VM/winbuild.iso" FALSE

[ -f "$STAGE/done.txt" ] || { echo "the build did not finish; see $STAGE/build.log if it exists" >&2; exit 1; }
[ -f "$STAGE/selftest.txt" ] || { echo "the build failed in Windows:" >&2; sed 's/\r$//' "$STAGE/build.log" | tail -15 >&2; exit 1; }
echo "--- self-test report from Windows"; sed 's/\r$//' "$STAGE/selftest.txt"
grep -q "self-test passed" "$STAGE/selftest.txt" || { echo "self-test FAILED; log: $STAGE/build.log" >&2; exit 1; }
grep -q "supplied with avOpenKit: True" "$STAGE/selftest.txt" || { echo "the build did not use its own FFmpeg" >&2; exit 1; }
mkdir -p dist && cp "$STAGE/avOpenKit-windows-x64.zip" dist/ && cp "$STAGE/build.log" dist/windows-build.log
ls -la dist/avOpenKit-windows-x64.zip
