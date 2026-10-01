#!/bin/bash
# Translation workflow (spec section 5a). Run from the project folder.
#
#   tools/update_translations.sh hi es      refresh avopenkit/i18n/avopenkit_<code>.ts from the
#                                           source, keeping translations already entered
#   tools/update_translations.sh            the same, for every .ts file already present
#
# A language is offered in the program only when its .qm exists, and a .qm is compiled here only
# for languages listed in avopenkit/i18n/reviewed.txt (one code per line) - that is, after a
# fluent speaker has checked the translation.
set -e
cd "$(dirname "$0")/.."
dir=avopenkit/i18n
mkdir -p "$dir"
lupdate=.venv/bin/pylupdate6
# Qt 6's lrelease; a bare "lrelease" on PATH may be a chooser that looks for Qt 5.
lrelease=/usr/lib/qt6/bin/lrelease
[ -x "$lrelease" ] || lrelease=$(command -v lrelease6 || command -v lrelease-qt6 || command -v lrelease)

codes=("$@")
if [ ${#codes[@]} -eq 0 ]; then
    for f in "$dir"/avopenkit_*.ts; do
        [ -e "$f" ] || continue
        c=${f##*avopenkit_}; codes+=("${c%.ts}")
    done
fi
for c in "${codes[@]}"; do
    "$lupdate" avopenkit --no-obsolete --ts "$dir/avopenkit_$c.ts"
done

rm -f "$dir"/avopenkit_*.qm
if [ -f "$dir/reviewed.txt" ]; then
    while read -r c; do
        [ -n "$c" ] && [ -f "$dir/avopenkit_$c.ts" ] && "$lrelease" -silent "$dir/avopenkit_$c.ts" -qm "$dir/avopenkit_$c.qm" && echo "compiled $c"
    done < "$dir/reviewed.txt"
fi
exit 0
