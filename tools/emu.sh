#!/usr/bin/env bash
# Local Android emulator helpers. Everything (AVD, emulator settings) stays under toolchain/.
#   tools/emu.sh create | start | wait | install <apk> | shot <name> | adb <args...> | stop
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SDK="$ROOT/toolchain/android-sdk"
export ANDROID_SDK_ROOT="$(cygpath -w "$SDK")"
export ANDROID_HOME="$ANDROID_SDK_ROOT"
export ANDROID_USER_HOME="$(cygpath -w "$ROOT/toolchain/android-user")"
export ANDROID_EMULATOR_HOME="$ANDROID_USER_HOME"
export ANDROID_AVD_HOME="$(cygpath -w "$ROOT/toolchain/android-user/avd")"
export JAVA_HOME="$(cygpath -w "$ROOT/toolchain/jdk/jdk-17.0.20.1+1")"
mkdir -p "$ROOT/toolchain/android-user/avd" "$ROOT/build/shots"
ADB="$SDK/platform-tools/adb.exe"
EMU="$SDK/emulator/emulator.exe"
AVD=rjecnik_test
cmd="${1:-}"; shift || true
case "$cmd" in
  create)
    echo no | cmd //c "$(cygpath -w "$SDK/cmdline-tools/latest/bin/avdmanager.bat")" create avd -n "$AVD" \
      -k "system-images;android-34;google_apis;x86_64" -d pixel_6 --force
    # more RAM/storage for the 50 MB dictionary copy
    CFG="$ROOT/toolchain/android-user/avd/$AVD.avd/config.ini"
    sed -i 's/^hw.ramSize=.*/hw.ramSize=3072/; s/^disk.dataPartition.size=.*/disk.dataPartition.size=4G/' "$CFG"
    grep -q '^hw.keyboard' "$CFG" && sed -i 's/^hw.keyboard=.*/hw.keyboard=yes/' "$CFG" || echo 'hw.keyboard=yes' >> "$CFG"
    ;;
  accel)
    "$EMU" -accel-check
    ;;
  start)
    "$EMU" -avd "$AVD" -no-window -no-snapshot -no-boot-anim -gpu swiftshader_indirect -netdelay none -netspeed full \
      > "$ROOT/build/emulator.log" 2>&1 &
    echo "emulator starting (log: build/emulator.log)"
    ;;
  wait)
    "$ADB" wait-for-device
    for i in $(seq 1 180); do
      if [ "$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then echo booted; exit 0; fi
      sleep 2
    done
    echo "boot timeout"; exit 1
    ;;
  install)
    "$ADB" install -r -g "$(cygpath -w "$1")"
    ;;
  shot)
    "$ADB" exec-out screencap -p > "$ROOT/build/shots/$1.png"
    echo "build/shots/$1.png"
    ;;
  adb)
    "$ADB" "$@"
    ;;
  stop)
    "$ADB" emu kill || true
    ;;
  *)
    echo "usage: $0 create|accel|start|wait|install <apk>|shot <name>|adb ...|stop"; exit 2
    ;;
esac
