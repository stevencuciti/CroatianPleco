#!/usr/bin/env bash
# Build the Rječnik APK with the plain Android SDK tools (no Gradle):
#   aapt2 (resources) -> javac -> d8 -> package dex + native libs + assets -> zipalign -> apksigner
#
# Usage: tools/build_apk.sh [--skip-native] [--skip-db]
# Env:   BUILD_DIR (default build/apk), VERSION_CODE, VERSION_NAME
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SDK="$ROOT/toolchain/android-sdk"
BT="$SDK/build-tools/35.0.0"
ANDROID_JAR="$SDK/platforms/android-35/android.jar"
export JAVA_HOME="$ROOT/toolchain/jdk/jdk-17.0.20.1+1"
export PATH="$JAVA_HOME/bin:$PATH"
OUT="${BUILD_DIR:-$ROOT/build/apk}"
VERSION_CODE="${VERSION_CODE:-1}"
VERSION_NAME="${VERSION_NAME:-1.0}"
KEYSTORE="$ROOT/toolchain/keystore/rjecnik.keystore"
DIST="$ROOT/dist"
SKIP_NATIVE=0; SKIP_DB=0
for a in "$@"; do
  case "$a" in
    --skip-native) SKIP_NATIVE=1 ;;
    --skip-db) SKIP_DB=1 ;;
  esac
done

win() { cygpath -w "$1"; }

rm -rf "$OUT"
mkdir -p "$OUT"/{gen,classes,dex,assets,staging/lib}

echo "== native library"
if [ "$SKIP_NATIVE" = 0 ] || [ ! -f "$ROOT/build/native/lib/arm64-v8a/libhrspeak.so" ]; then
  bash "$ROOT/tools/build_native.sh"
fi
cp -r "$ROOT/build/native/lib/." "$OUT/staging/lib/"

echo "== dictionary database"
if [ "$SKIP_DB" = 0 ] || [ ! -f "$ROOT/build/db/dict.db" ]; then
  python -I "$ROOT/tools/build_db.py" "$ROOT/data/work" "$ROOT/data/enrich" "$ROOT/build/db/dict.db"
fi
cp "$ROOT/build/db/dict.db" "$OUT/assets/dict.db"

echo "== eSpeak NG voice data (Croatian + English only)"
ESD="$ROOT/third_party/espeak-apk-extract/data/espeak-ng-data"
DST="$OUT/assets/espeak-ng-data"
mkdir -p "$DST/lang/zls" "$DST/lang/gmw" "$DST/voices/!v"
cp "$ESD"/{phondata,phonindex,phontab,intonations,hr_dict,en_dict} "$DST/"
cp "$ESD/lang/zls/hr" "$DST/lang/zls/"
cp "$ESD/lang/gmw/en" "$ESD/lang/gmw/en-GB" "$DST/lang/gmw/" 2>/dev/null || cp "$ESD/lang/gmw/en" "$DST/lang/gmw/"
cp "$ESD/voices/!v/"{m1,m3,f2,f3} "$DST/voices/!v/" 2>/dev/null || true

echo "== resources (aapt2)"
"$BT/aapt2.exe" compile --dir "$(win "$ROOT/app/res")" -o "$(win "$OUT/res.zip")"
"$BT/aapt2.exe" link -o "$(win "$OUT/base.apk")" \
  -I "$(win "$ANDROID_JAR")" \
  --manifest "$(win "$ROOT/app/AndroidManifest.xml")" \
  --java "$(win "$OUT/gen")" \
  -A "$(win "$OUT/assets")" \
  --min-sdk-version 24 --target-sdk-version 35 \
  --version-code "$VERSION_CODE" --version-name "$VERSION_NAME" \
  --auto-add-overlay \
  "$(win "$OUT/res.zip")"

echo "== javac"
find "$ROOT/app/src" "$OUT/gen" -name '*.java' > "$OUT/sources.txt"
while read -r f; do printf '"%s"
' "$(cygpath -m "$f")"; done < "$OUT/sources.txt" > "$OUT/sources_win.txt"
javac -encoding UTF-8 -source 1.8 -target 1.8 -Xlint:-options -Xlint:deprecation -Xlint:unchecked \
  -bootclasspath "$(win "$ANDROID_JAR");$(win "$BT/core-lambda-stubs.jar")" -classpath "$(win "$ANDROID_JAR")" \
  -d "$(win "$OUT/classes")" @"$(win "$OUT/sources_win.txt")"

echo "== d8"
( cd "$OUT/classes" && jar cf "$(win "$OUT/classes.jar")" . )
java -Xmx2g -cp "$(win "$BT/lib/d8.jar")" com.android.tools.r8.D8 --release --min-api 24 --lib "$(win "$ANDROID_JAR")"   --output "$(win "$OUT/dex")" "$(win "$OUT/classes.jar")"

echo "== package"
python -I "$ROOT/tools/apk_package.py" "$OUT/base.apk" "$OUT/unsigned.apk" "$OUT/dex" "$OUT/staging"
"$BT/zipalign.exe" -p -f 4 "$(win "$OUT/unsigned.apk")" "$(win "$OUT/aligned.apk")"

echo "== sign"
mkdir -p "$DIST"
java -jar "$(win "$BT/lib/apksigner.jar")" sign --ks "$(win "$KEYSTORE")" --ks-key-alias rjecnik \
  --ks-pass pass:rjecnik-local --key-pass pass:rjecnik-local \
  --out "$(win "$OUT/rjecnik.apk")" "$(win "$OUT/aligned.apk")"
java -jar "$(win "$BT/lib/apksigner.jar")" verify --print-certs "$(win "$OUT/rjecnik.apk")" | head -3
cp "$OUT/rjecnik.apk" "$DIST/Rjecnik-$VERSION_NAME.apk"
ls -la "$DIST/Rjecnik-$VERSION_NAME.apk"
