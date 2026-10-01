#!/usr/bin/env bash
# Build the User Guide in A4 and A5, each as a styled PDF and an editable ODT.
#   docs/build_guide.sh
# Before building, refresh what comes from the program itself:
#   .venv/bin/python tools/make_guide_assets.py reference      (commands in Part 7)
#   .venv/bin/python tools/make_guide_assets.py screenshots    (docs/img/*.png)
set -euo pipefail
cd "$(dirname "$0")"
TMP="$(mktemp -d -p "$PWD" .build.XXXX)"
trap 'rm -rf "$TMP"' EXIT

# Headless Chrome must not write its font cache into the desktop's (see ~/.claude memory:
# Plasma crash = Chrome poisons fontconfig cache). Use the private configuration if present.
if [ -f "$HOME/.config/fontconfig-chrome/fonts.conf" ]; then
    export FONTCONFIG_FILE="$HOME/.config/fontconfig-chrome/fonts.conf"
else
    export XDG_CACHE_HOME="$TMP/cache"
fi

build () {   # suffix  page-css  odt-width  odt-height  odt-margin  odt-body-font
    local out="avOpenKit-User-Guide$1"
    pandoc USER_GUIDE.md -s --embed-resources --resource-path=. --toc --toc-depth=2 \
        --css guide.css --css "$2" -o "$TMP/guide$1.html"
    google-chrome --headless=new --disable-gpu --no-pdf-header-footer \
        --print-to-pdf="$PWD/$out.pdf" "file://$TMP/guide$1.html" 2>/dev/null

    # pandoc writes US Letter; patch the page size (see ~/.claude memory: pandoc ODT gotchas)
    pandoc USER_GUIDE.md --resource-path=. --toc --toc-depth=2 -o "$TMP/guide$1.odt"
    rm -rf "$TMP/x" && mkdir "$TMP/x" && (cd "$TMP/x" && unzip -q "../guide$1.odt")
    python3 - "$TMP/x/styles.xml" "$3" "$4" "$5" "$6" <<'PY'
import re, sys
p, w, h, m, font = sys.argv[1:6]
s = open(p).read()
s = s.replace('fo:font-size="12pt"', f'fo:font-size="{font}"')        # body text
def fix(match):
    t = match.group(0)
    for a, b in [('fo:page-width="8.5in"', f'fo:page-width="{w}"'), ('fo:page-height="11in"', f'fo:page-height="{h}"'),
                 ('fo:margin-top="1in"', f'fo:margin-top="{m}"'), ('fo:margin-bottom="1in"', f'fo:margin-bottom="{m}"'),
                 ('fo:margin-left="1in"', f'fo:margin-left="{m}"'), ('fo:margin-right="1in"', f'fo:margin-right="{m}"')]:
        t = t.replace(a, b)
    return t
s, n = re.subn(r'<style:page-layout-properties[^>]*>', fix, s)
assert n == 1
open(p, 'w').write(s)

# pandoc sizes pictures from their pixel count, which makes a 2000-pixel screenshot half a metre
# wide. Scale each to the text column: a full-window screenshot (2000 px) fills it, and the
# smaller dialogs keep their size relative to that.
c = p.replace("styles.xml", "content.xml")
t = open(c).read()
column = float(w[:-2]) - 2 * float(m[:-2])                             # cm
def size(match):
    width, height = float(match.group(1)), float(match.group(2))      # points = pixels * 0.75
    new = column * min(1.0, width / 1500.0)
    return f'svg:width="{new:.2f}cm" svg:height="{new * height / width:.2f}cm"'
t, n = re.subn(r'svg:width="([\d.]+)pt" svg:height="([\d.]+)pt"', size, t)
assert n == 8, n
open(c, 'w').write(t)
PY
    rm -f "$out.odt"
    (cd "$TMP/x" && zip -q -X -0 "$OLDPWD/$out.odt" mimetype && zip -q -X -r "$OLDPWD/$out.odt" . -x mimetype)
    printf '%-32s ' "$out.pdf"
    pdfinfo "$out.pdf" | awk '/^Pages/{p=$2}/^Page size/{printf "%s pages, %.0f x %.0f mm\n", p, $3*0.3528, $5*0.3528}'
}

build ""    guide-a4.css 21cm   29.7cm 2cm   11pt
build "-A5" guide-a5.css 14.8cm 21cm   1.3cm 9.5pt
