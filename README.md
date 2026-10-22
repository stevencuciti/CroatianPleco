# Rječnik — offline English · Croatian · Kajkavian dictionary for Android

A Pleco-style dictionary app: search in English, standard Croatian or Kajkavian, with full definitions,
inflection tables, example sentences, Međimurje Kajkavian equivalents and pronunciation, all of it offline.

**Install:** copy `dist/Rjecnik-1.0.apk` to your phone, open it, and allow "Install unknown apps" for the file
manager or browser you open it from. Android 7.0 or later.

**Better pronunciation (optional):** the app always has a built-in offline voice (eSpeak NG, robotic). For a natural
voice, install a Croatian voice for your phone's text-to-speech engine once (e.g. *Settings → Text-to-speech →
Speech Services by Google → Install voice data → Croatian*). After that, the app uses it offline automatically.
*Settings → Pronunciation* in the app shows which voice is in use.

## Content

| Part | Source |
|---|---|
| Headwords, English definitions, inflection tables, IPA, etymology, synonyms, Wiktionary examples, Wiktionary Kajkavian/Chakavian entries | English Wiktionary (Serbo-Croatian entries, Croatian/Latin script; Serbian-only and ekavian senses removed) via the kaikki.org / wiktextract extract, CC BY-SA 4.0 |
| Example sentences, commonness ratings, Međimurje Kajkavian equivalents + Kajkavian example sentences | **AI-generated** (Claude), then checked by automated QA heuristics and a targeted AI correction pass for flagged entries (a full second-AI review only ran on a small subset). Not checked by a human. May contain mistakes, so verify with a native speaker, especially Kajkavian forms marked *low confidence*. |
| Speech | Phone's text-to-speech engine when a Croatian voice is installed; otherwise eSpeak NG 1.52 (GPL-3.0-or-later), compiled into the app |

Because the app links eSpeak NG, the app as a whole is distributed under the GPL-3.0.

## Building

Everything builds with the local toolchain in `toolchain/` (JDK 17, Android SDK 35, NDK r28, CMake). No Gradle.

```bash
bash tools/build_apk.sh            # native lib + database + APK -> dist/Rjecnik-<version>.apk
bash tools/build_apk.sh --skip-native --skip-db   # reuse previously built lib/db
```

Pipeline:

1. `tools/build_entries.py`: kaikki.org Serbo-Croatian JSONL → `data/work/entries.jsonl` (filtering, accents,
   inflection tables) + `formmap.jsonl`.
2. `tools/make_batches.py`: batches for the AI pass (`data/enrich/batches`).
3. `tools/enrich_workflow.js`: generate + review workflow (examples, commonness, Međimurje Kajkavian) →
   `data/enrich/out`, `data/enrich/review`.
4. `tools/qa_enrichment.py`: heuristic QA flags for a targeted fix pass.
5. `tools/build_db.py`: SQLite database with search indexes → `build/db/dict.db` (shipped as `assets/dict.db`).
6. `tools/build_native.sh`: eSpeak NG + JNI bridge → `libhrspeak.so` for arm64-v8a, armeabi-v7a, x86_64.
7. `tools/build_apk.sh`: aapt2 → javac → d8 → package → zipalign → apksigner.

App source: `app/` (plain Java, Android framework only). Spec: `docs/APP_SPEC.md`.
Tests: `tools/search_sim.py` (Python port of the search ranking), `tools/emu.sh` (local emulator helper).
