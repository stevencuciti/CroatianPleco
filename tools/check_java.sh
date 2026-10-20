#!/usr/bin/env bash
# Fast compile check (aapt2 + javac, no dex/packaging).
#   MODULE=main tools/check_java.sh app/src/hr/rjecnik/ui/MainActivity.java ...
# Compiles the core sources (App, data/, audio/, ui/{Prefs,Ui,BaseActivity,Nav}) plus the given files.
# With MODULE set, resource files prefixed by another screen module (main_/entry_/lists_/settings_/about_,
# values/strings_<module>.xml) are left out, so other modules' work-in-progress cannot break the check.
# With no file arguments every source under app/src is compiled.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SDK="$ROOT/toolchain/android-sdk"
BT="$SDK/build-tools/35.0.0"
ANDROID_JAR="$SDK/platforms/android-35/android.jar"
export JAVA_HOME="$ROOT/toolchain/jdk/jdk-17.0.20.1+1"
export PATH="$JAVA_HOME/bin:$PATH"
OUT="${BUILD_DIR:-$ROOT/build/check_${MODULE:-all}}"
win() { cygpath -w "$1"; }
rm -rf "$OUT"; mkdir -p "$OUT/res" "$OUT/gen" "$OUT/classes"
MODS="main entry lists settings about"
( cd "$ROOT/app/res"
  find . -type f | while read -r f; do
    base="$(basename "$f")"; keep=1
    if [ -n "${MODULE:-}" ]; then
      for m in $MODS; do
        [ "$m" = "$MODULE" ] && continue
        case "$base" in "${m}_"*|"strings_${m}.xml") keep=0 ;; esac
      done
    fi
    if [ "$keep" = 1 ]; then mkdir -p "$OUT/res/$(dirname "$f")"; cp "$f" "$OUT/res/$f"; fi
  done )
MANIFEST="$ROOT/app/AndroidManifest.xml"
if [ -n "${MODULE:-}" ] && ! grep -rq 'name="main_lookup_label"' "$OUT/res"; then :; fi
"$BT/aapt2.exe" compile --dir "$(win "$OUT/res")" -o "$(win "$OUT/res.zip")"
"$BT/aapt2.exe" link -o "$(win "$OUT/base.apk")" -I "$(win "$ANDROID_JAR")" --manifest "$(win "$MANIFEST")" \
  --java "$(win "$OUT/gen")" --min-sdk-version 24 --target-sdk-version 35 --auto-add-overlay "$(win "$OUT/res.zip")"
SRC="$ROOT/app/src/hr/rjecnik"
if [ "$#" -gt 0 ]; then
  { find "$SRC/data" "$SRC/audio" -name '*.java'
    ls "$SRC/App.java" "$SRC/ui/Prefs.java" "$SRC/ui/Ui.java" "$SRC/ui/BaseActivity.java" "$SRC/ui/Nav.java"
    for f in "$@"; do realpath "$f"; done
    find "$OUT/gen" -name '*.java'; } | sort -u > "$OUT/sources.txt"
else
  find "$ROOT/app/src" "$OUT/gen" -name '*.java' > "$OUT/sources.txt"
fi
while read -r f; do printf '"%s"
' "$(cygpath -m "$f")"; done < "$OUT/sources.txt" > "$OUT/sources_win.txt"
javac -encoding UTF-8 -source 1.8 -target 1.8 -Xlint:-options -Xlint:deprecation -Xlint:unchecked -Xmaxerrs 1000 \
  -bootclasspath "$(win "$ANDROID_JAR");$(win "$BT/core-lambda-stubs.jar")" -classpath "$(win "$ANDROID_JAR")" \
  -d "$(win "$OUT/classes")" @"$(win "$OUT/sources_win.txt")"
echo "CHECK OK ($(wc -l < "$OUT/sources.txt") sources)"
