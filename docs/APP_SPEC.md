# Rječnik — offline English · Croatian · Kajkavian dictionary (Android)

Pleco-style dictionary app. **Plain Java + Android framework only** (no AndroidX, no Kotlin, no Gradle, no
third-party Java libraries). Built by `tools/build_apk.sh` with aapt2 → javac → d8 → zipalign → apksigner.

* `compileSdk`/`targetSdk` 35, `minSdk` 24. Java source level 11 (`javac --release 11` against `android.jar`; no
  records, no `var` is fine to use but keep code plain). Only framework APIs that exist on API 24, or guard with
  `Build.VERSION.SDK_INT` checks.
* Package / applicationId: `hr.rjecnik`. Launcher label: **Rječnik**.
* No `INTERNET` permission — the app is fully offline.
* Source root: `app/src/hr/rjecnik/...`, resources `app/res/...`, manifest `app/AndroidManifest.xml`,
  assets `app/assets/` (generated at build time: `dict.db`, `espeak-ng-data/...`).
* Use `org.json` (built into Android) for JSON. Use `android.database.sqlite` for SQLite.
* All UI text in English, with Croatian words shown as data. Support light + dark (`values-night`).

## Directory / package layout

```
app/AndroidManifest.xml
app/res/values/{strings.xml, colors.xml, themes.xml, dimens.xml}
app/res/values-night/{colors.xml, themes.xml}
app/res/drawable/*.xml                 (vector icons, shapes — no PNGs needed except launcher)
app/res/mipmap-anydpi-v26/ic_launcher.xml + drawable foreground/background vectors
app/res/layout/*.xml
app/src/hr/rjecnik/App.java
app/src/hr/rjecnik/data/{TextNorm, DictionaryDb, SearchResult, Entry, UserStore}.java
app/src/hr/rjecnik/audio/{Speech, EspeakNative, EspeakPlayer}.java
app/src/hr/rjecnik/ui/{MainActivity, ResultsAdapter, EntryActivity, EntryRenderer, ListsActivity,
                       SettingsActivity, AboutActivity, Ui, Prefs}.java
app/jni/{CMakeLists.txt, espeak_jni.c}  (already written — native lib name "hrspeak")
```

## Offline database `assets/dict.db` (built by `tools/build_db.py`)

Copied on first launch (and whenever `meta.db_version` or the APK's versionCode changes) from assets to
`getNoBackupFilesDir()/dict.db` (stream copy, then open read-only with `SQLiteDatabase.openDatabase(path, null,
OPEN_READONLY | NO_LOCALIZED_COLLATORS)`).

```
meta(key TEXT PRIMARY KEY, value TEXT)          keys: db_version, entries, entries_enriched, source, kajkavian_variety
entries(id INTEGER PRIMARY KEY, headword TEXT, accented TEXT, pos TEXT, gram TEXT, dialect TEXT,
        freq INTEGER, gloss TEXT, kaj TEXT, data BLOB)
hr_index(term TEXT, entry_id INTEGER, kind INTEGER, form TEXT, info TEXT)     INDEX on term
en_index(term TEXT, entry_id INTEGER, weight INTEGER)                        INDEX on term
```

* `headword` plain Croatian (no tonal accents) e.g. `kuća`; `accented` with Wiktionary tonal accents e.g. `kȕća`.
* `pos`: noun, verb, adj, adv, name, pron, prep, conj, num, intj, particle, phrase, proverb, contraction, …
* `gram`: e.g. `f`, `m anim`, `n`, `impf`, `pf`, `impf/pf` (may be empty).
* `dialect`: `std` (standard Croatian), `kaj` (Kajkavian entry), `cak` (Chakavian entry).
* `freq`: 1..5 commonness (5 = very common).
* `gloss`: short English summary for result rows. `kaj`: Međimurje Kajkavian equivalent(s) for result rows (may be empty).
* `data`: **zlib-deflated** (standard zlib header — `java.util.zip.Inflater` with default `nowrap=false`) UTF-8 JSON:

```jsonc
{
  "w": "pas", "a": "pȁs", "p": "noun", "g": "m anim", "d": "std",
  "ipa": "/pâs/", "hy": "pas",
  "s": [                                   // senses (Wiktionary), in order
    {"g": "dog", "l": "label text e.g. transitive, colloquial", "ex": [{"hr": "Volim svog psa.", "en": "I love my dog.", "ref": "", "src": "wikt"}],
     "syn": ["..."], "ant": ["..."], "see": ["target headword"]}
  ],
  "ax": [{"hr": "...", "en": "...", "src": "ai"}],   // AI-generated example sentences (standard Croatian; dialect for kaj/cak entries)
  "std": "jučer",                                    // only kaj/cak entries: standard Croatian equivalent(s)
  "k": {"w": "pes", "n": "note", "c": "h|m|l", "src": "ai", "ex": {"t": "Kajkavian sentence", "en": "English"}},  // Međimurje Kajkavian (AI)
  "kw": ["pes"],                                     // Kajkavian forms attested on Wiktionary
  "t": [{"title": "Declension", "cols": ["", "Singular", "Plural"], "rows": [["Nominative", "pȁs", "psȉ"], ...]}],
  "alt": [{"form": "dober", "label": "Kajkavian"}],  // alternative forms with labels
  "rel": {"Diminutive": ["psȉć"], "Relational adjective": ["pȁsjī"]},   // ordered map label -> words
  "syn": [], "ant": [], "der": [], "relw": [],      // entry-level synonyms/antonyms/derived/related words
  "ety": "Inherited from Proto-Slavic *pьsъ."
}
```
Every key except `w`, `p`, `s` may be missing. Words inside `syn/ant/der/relw/rel/see/std` may carry tonal accents —
pass them through `TextNorm.stripAccents` before looking them up.

### Search keys
`hr_index.term` and `en_index.term` are pre-normalised:
* hr: `TextNorm.fold(s)` — tonal accents stripped, lower case, `č ć → c`, `š → s`, `ž → z`, `đ → dj`, other
  non-[0-9a-z ə-] chars → space, whitespace collapsed. A second key with `đ → d` is also stored.
  `kind`: 0 headword, 1 Kajkavian form, 2 inflected form, 3 alternative form / standard equivalent.
  `form` is the matched form with diacritics, `info` a short grammatical description e.g. `gen. sg.`.
* en: `TextNorm.enNorm(s)` — NFKD, strip combining marks, lower case, `’`→`'`, other non-[a-z0-9' -] → space,
  collapse spaces. Rows are whole gloss phrases (`to go`, `go`, `house`) with weight ≈ 1000 − 40·sense − 4·phrase,
  and single keywords with weight ≈ 500 − 40·sense.

## Class contracts

### `hr.rjecnik.App extends android.app.Application`
```java
public static App get();                       // set in onCreate
public DictionaryDb db();                      // lazily opened, thread-safe (synchronized)
public UserStore user();
public Speech speech();                        // lazily created
public java.util.concurrent.ExecutorService io();   // single shared background executor (4 threads)
public android.os.Handler main();              // main-looper handler
```

### `hr.rjecnik.data.TextNorm` (final, static methods; must match tools/hrtext.py exactly)
```java
public static String stripAccents(String s);   // remove U+0300 0301 0302 0304 0306 030F 0311 0325 only when they follow a vowel aeiouAEIOU, r/R or ə (keeps č ć š ž đ). NFD→filter→NFC.
public static String fold(String s);           // see "Search keys"
public static String foldD(String s);          // fold with đ→d
public static String enNorm(String s);
public static boolean hasCroatianLetters(String s);   // contains č ć š ž đ (any case)
```

### `hr.rjecnik.data.SearchResult` (plain data class, public final fields)
```java
public final long id; public final String headword, accented, pos, gram, dialect, gloss, kaj;
public final int freq;
public final int matchType;      // MATCH_HR_HEAD=0, MATCH_KAJ=1, MATCH_HR_FORM=2, MATCH_ALT=3, MATCH_EN=4, MATCH_HR_PREFIX=5, MATCH_EN_PREFIX=6
public final String matchedForm; // form that matched (for forms/kaj/alt), else null
public final String matchInfo;   // e.g. "gen. sg." or "Međimurje Kajkavian", else null
public final int score;
public SearchResult(long id, String headword, String accented, String pos, String gram, String dialect,
                    String gloss, String kaj, int freq, int matchType, String matchedForm, String matchInfo, int score);
```

### `hr.rjecnik.data.DictionaryDb`
```java
public static final int MODE_AUTO = 0, MODE_HR = 1, MODE_EN = 2;
public static DictionaryDb open(android.content.Context ctx) throws java.io.IOException;  // copy-if-needed + open
public java.util.List<SearchResult> search(String query, int mode, int limit);  // never null; safe to call off main thread
public Entry getEntry(long id);                     // null if missing
public java.util.List<SearchResult> lookupHeadword(String word);   // exact (folded) headword/kind 0 matches, for cross-links
public SearchResult randomCommonEntry(long seed);   // e.g. "word of the day": freq>=4, std, deterministic by seed
public String meta(String key);
public int entryCount();
```
Search algorithm (implement exactly, all SQL parameterised):
1. `q = query.trim()`; empty → empty list. `qf = TextNorm.fold(q)`, `qe = TextNorm.enNorm(q)`.
2. Croatian (modes AUTO, HR): exact rows `SELECT entry_id, kind, form, info FROM hr_index WHERE term = ? LIMIT 300` on
   qf. Score: kind0 → 1000, kind1 → 920, kind2 → 860, kind3 → 820. If `qf.length() >= 1`, prefix rows
   `SELECT entry_id, kind, term, form FROM hr_index WHERE term > ? AND term < ? AND kind IN (0,1) ORDER BY term LIMIT 400`
   with bounds `qf` and `qf + "￿"`; score 600 − 4·(term.length − qf.length) (min 300), matchType HR_PREFIX (or KAJ when kind 1).
3. English (modes AUTO, EN): exact `SELECT entry_id, weight FROM en_index WHERE term = ? ORDER BY weight DESC LIMIT 400`
   on qe → score = 300 + weight·0.7 (so whole-phrase match on sense 1 ≈ 1000). If qe.length() >= 2, prefix rows
   `... WHERE term > ? AND term < ? ORDER BY weight DESC LIMIT 300` → score 200 + weight·0.35, matchType EN_PREFIX.
4. In AUTO mode, if `TextNorm.hasCroatianLetters(q)` subtract 400 from English scores.
5. Add `freq * 12` to every score; +40 for a headword match when the query contains č/ć/š/ž/đ and equals the headword exactly (case-insensitive, accents stripped); for `pos == "name"` subtract 60; for dialect `kaj`/`cak` subtract 20 unless the
   match is kind 0 or 1.
6. Keep the best-scoring match per entry_id; sort by score desc, then freq desc, then headword length asc; cut to
   `limit`; then load summary columns (`id, headword, accented, pos, gram, dialect, freq, gloss, kaj`) with one
   `WHERE id IN (...)` query.

### `hr.rjecnik.data.Entry` (parsed `data` JSON; public final fields, all non-null, lists possibly empty)
```java
public static final class Example { public final String text, english, ref, source; }   // source "wikt" | "ai"
public static final class Sense { public final String gloss, labels; public final java.util.List<Example> examples;
                                  public final java.util.List<String> synonyms, antonyms, see; }
public static final class Kajkavian { public final String words, note, confidence /*h|m|l*/, source;
                                      public final Example example; /* may be null */ }
public static final class Table { public final String title; public final java.util.List<String> cols;
                                  public final java.util.List<java.util.List<String>> rows; }
public static final class Form { public final String form, label; }
public final long id; public final String headword, accented, pos, gram, dialect, ipa, hyphenation, etymology, standard;
public final int freq;
public final java.util.List<Sense> senses; public final java.util.List<Example> aiExamples;
public final Kajkavian kajkavian;               // null if none
public final java.util.List<String> wiktKajkavian;
public final java.util.List<Table> tables; public final java.util.List<Form> alternatives;
public final java.util.LinkedHashMap<String, java.util.List<String>> related;
public final java.util.List<String> synonyms, antonyms, derived, relatedWords;
public static Entry parse(long id, int freq, byte[] deflatedJson) throws org.json.JSONException, java.util.zip.DataFormatException;
```

### `hr.rjecnik.data.UserStore` (SQLiteOpenHelper over `user.db`; bookmarks + history)
```java
public UserStore(android.content.Context ctx);
public boolean isBookmarked(long entryId);
public void setBookmarked(long entryId, String headword, String gloss, boolean on);
public void addHistory(long entryId, String headword, String gloss);   // upsert, newest first, keep last 500
public java.util.List<Item> bookmarks();      // newest first
public java.util.List<Item> history(int limit);
public void clearHistory();
public static final class Item { public final long entryId; public final String headword, gloss; public final long time; }
```

### Audio — `hr.rjecnik.audio`
```java
public final class Speech {
  public static final int LANG_HR = 0, LANG_KAJ = 1, LANG_EN = 2;
  public static final int ENGINE_AUTO = 0, ENGINE_SYSTEM = 1, ENGINE_ESPEAK = 2;
  public Speech(android.content.Context ctx);
  public void speak(String text, int lang);   // stops anything playing first; never throws; main or any thread
  public void stop();
  public void setEngine(int engine); public void setRate(float rate /*0.5..1.5, 1 = normal*/);
  public boolean systemCroatianAvailable();   // offline Croatian system voice found (after init)
  public String describeStatus();             // human text for Settings, e.g. "Phone voice: Croatian (offline) via Google" / "Built-in eSpeak NG"
  public interface Listener { void onSpeechStateChanged(); }
  public void setListener(Listener l);
  public void shutdown();
}
```
* System TTS: `new TextToSpeech(ctx, listener)` with the default engine; after init check a Croatian voice:
  `Locale("hr","HR")` via `getVoices()` (API 21+) — accept voices whose locale language is `hr` (also accept `bs`/`sr`
  Latin only if no `hr`) and `!isNetworkConnectionRequired()` and no `notInstalled` feature
  (`TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED`). If the default engine has none but another installed engine
  (`getEngines()`, e.g. `com.google.android.tts`) might, create a second `TextToSpeech` bound to that engine package and
  check it too. English: any offline `en` voice (prefer en-GB / en-US).
* ENGINE_AUTO: use system voice when an offline voice for that language exists, otherwise eSpeak. ENGINE_SYSTEM:
  system only (fall back to eSpeak if none). ENGINE_ESPEAK: always eSpeak.
* Kajkavian text (LANG_KAJ) is spoken with the Croatian voice.
* `EspeakNative`: `static { System.loadLibrary("hrspeak"); }` guarded (catch `UnsatisfiedLinkError` → unavailable).
  Native methods (exact signatures, implemented in app/jni/espeak_jni.c):
  `static native int nativeInit(String dataParentDir); static native boolean nativeSetVoice(String name);
   static native short[] nativeSynth(String text, int ratewpm, int pitch0to99);`
  Before init, copy assets folder `espeak-ng-data/` (recursively; use `AssetManager.list`) to
  `getNoBackupFilesDir()/espeak/espeak-ng-data/` once per versionCode; pass the parent dir
  (`.../espeak`). Voices: `"hr"` for LANG_HR/LANG_KAJ, `"en-gb"` (fallback `"en"`) for LANG_EN.
  Rate: 175 wpm × rate setting; pitch 50. All native calls synchronised on one lock, run on a dedicated
  `HandlerThread`. Returns mono 16-bit PCM at the sample rate returned by `nativeInit` (22050).
* `EspeakPlayer`: plays short[] PCM via `AudioTrack` (MODE_STATIC, `AudioAttributes.USAGE_MEDIA`,
  `CONTENT_TYPE_SPEECH`), releases previous track on new speak/stop.

### UI — `hr.rjecnik.ui`
* **MainActivity** (launcher, `windowSoftInputMode="stateVisible|adjustResize"`): top bar with app title + overflow
  (Bookmarks, History, Settings, About). Search field (EditText, single line, `imeOptions=actionSearch`, hint
  "Search English, hrvatski or kajkavski", clear (×) button). Below it a segmented mode selector: **Auto · HR→EN ·
  EN→HR** (persisted in Prefs). Results `ListView` with `ResultsAdapter`. Search runs as you type: debounce
  120 ms, run on `App.io()`, discard stale results (sequence counter), post to main. Empty query: show
  "Word of the day" card (from `randomCommonEntry(daysSinceEpoch)`) and recent history list; tapping opens entry.
  Handles `Intent.ACTION_SEND`/`ACTION_PROCESS_TEXT` text as a query (manifest intent filters for
  `android.intent.action.PROCESS_TEXT` text/plain) so users can look up selected text from other apps.
* **ResultsAdapter**: row = headword (large, bold) + accented form small grey (if Prefs.showAccents and differs) +
  dialect badge (KAJ / ČAK coloured pill) + pos/gram small caps; line 2 English gloss (2 lines max, ellipsize);
  line 3 (optional) "Kajk. (Međimurje): pes" in accent colour if `kaj` non-empty and Prefs.showKajkavian;
  if matchType is HR_FORM/ALT/KAJ show "‹matchedForm› — ‹matchInfo›" chip above gloss. Speaker icon button
  on the right speaks the headword (LANG_HR, or LANG_KAJ for kaj/cak entries).
* **EntryActivity** (`EXTRA_ID` long; also `EXTRA_WORD` String to resolve via `lookupHeadword`): scrollable entry
  built by **EntryRenderer** (programmatic views, no WebView):
  1. Header: headword (28sp), accented form + IPA + hyphenation line, pos · gram · dialect badge, commonness
     dots (●●●○○), speaker button (normal) and slow button (rate 0.6), bookmark star in the top bar.
  2. **Definitions**: numbered senses, labels in italic grey before gloss; each Wiktionary example under its sense
     (Croatian bold-ish, English below, speaker icon, small "Wiktionary" source tag; quotations show `ref` in
     small italic). `see` items are tappable links → open that headword.
  3. **Examples** (AI): list of example pairs with speaker icons and an "AI-generated" tag.
  4. **Kajkavian (Međimurje)** card: words big, confidence chip ("high/medium/low confidence"), note, example
     (Kajkavian + English + speaker LANG_KAJ), "AI-generated — verify with a native speaker" footnote; plus
     "Wiktionary: dober" line for `kw`. For kaj/cak entries instead show **Standard Croatian** card with `std`
     (tappable → open that word).
  5. **Inflection** tables: each table a titled section; first table expanded, the rest collapsed (tap header to
     toggle). Render as `TableLayout` inside `HorizontalScrollView`; cells strip accents unless Prefs.showAccents.
  6. **Related**: `rel` map, synonyms, antonyms, derived, related words — as flow of tappable chips (custom
     FlowLayout ViewGroup in `Ui`), each opens the word.
  7. **Alternative forms** with labels; 8. **Etymology**; 9. Source footer: "Wiktionary (CC BY-SA 4.0)" and, if any
     AI content, "Includes AI-generated content".
  Adds to history on open. Long-press any Croatian text → copy to clipboard (toast).
* **ListsActivity** (`EXTRA_TAB` "bookmarks"|"history"): two-tab header (Bookmarks / History), list of items,
  tap opens entry, long-press removes bookmark; "Clear history" menu action with confirmation dialog.
* **SettingsActivity**: plain layout (no PreferenceFragment): Voice engine (Auto / Phone voice / Built-in eSpeak)
  radio group; speech speed SeekBar (0.5–1.5); status text from `Speech.describeStatus()`; buttons "Install
  Croatian phone voice" (`TextToSpeech.Engine.ACTION_INSTALL_TTS_DATA`, catch ActivityNotFoundException) and
  "Text-to-speech settings" (`com.android.settings.TTS_SETTINGS`); "Test voice" button speaking "Dobar dan! Kak
  ste?"; switches: show tonal accent marks, show Kajkavian, theme (Follow system / Light / Dark via
  `Prefs.applyTheme`); "Clear history".
* **AboutActivity**: app description, entry counts from `meta`, data sources & licences: Wiktionary contributors
  (CC BY-SA 4.0, https://en.wiktionary.org), kaikki.org (Tatu Ylonen, wiktextract), eSpeak NG (GPLv3), and the
  AI disclosure: "Example sentences, commonness ratings and Međimurje Kajkavian equivalents were generated with
  AI (Claude by Anthropic) and reviewed by AI only. They may contain mistakes — verify with a native speaker."
* **Prefs** (static helpers over default SharedPreferences): `searchMode`, `showAccents` (default true),
  `showKajkavian` (default true), `voiceEngine`, `speechRate`, `theme` (0 system, 1 light, 2 dark);
  `applyTheme(Activity)` — call in every Activity's `onCreate` before `setContentView`: picks `R.style.Theme_Rjecnik`
  (DayNight resolved via `values-night`) and, if forced light/dark, overrides `Configuration.uiMode` via
  `createConfigurationContext` is NOT needed — instead use two explicit themes `Theme_Rjecnik_Light`,
  `Theme_Rjecnik_Dark` and `Theme_Rjecnik` (follows system via values-night). 
* **Ui**: `dp(Context,int)`, `color(Context,int attrOrRes)`, `badge(Context, String text, int bgColor)`,
  `chip(Context, String text, View.OnClickListener)`, `speakerButton(Context, Runnable)`, `FlowLayout` (static
  nested public class extending ViewGroup), `copyToClipboard(Context, String)`.

## Visual design
Clean, calm, content-first (like Pleco): white / near-black backgrounds, one accent colour (Adriatic blue
`#1565C0` light, `#90CAF9` dark), Kajkavian accent (warm terracotta `#B5532A` light / `#FFAB91` dark), Chakavian
(teal `#00796B` / `#80CBC4`). Croatian text in the default sans; English glosses slightly smaller and secondary
colour. Generous line spacing, 16dp gutters, 48dp touch targets, ripple backgrounds
(`?android:attr/selectableItemBackgroundBorderless`). Use `android:Theme.Material.Light.NoActionBar` /
`android:Theme.Material.NoActionBar` parents and a custom top bar layout (title + icon buttons) so every Activity looks
consistent. Status bar colour = surface colour (with light status bar icons in light theme on API 23+).

## Resource ids shared between modules
Each module creates the layouts/strings it needs, prefixed by module to avoid clashes:
`main_*` (MainActivity/ResultsAdapter), `entry_*`, `lists_*`, `settings_*`, `about_*`. Shared resources
(colors, themes, dimens, drawables `ic_*`) live in `values/colors.xml`, `values/themes.xml`,
`values/dimens.xml`, `drawable/ic_*.xml` and are created by the **resources** module only.
Shared colour names (`@color/...`): `bg`, `surface`, `surface_alt`, `text_primary`, `text_secondary`, `divider`,
`accent`, `on_accent`, `kaj`, `kaj_bg`, `cak`, `cak_bg`, `ai_tag`, `wikt_tag`, `star`.
Shared drawables: `ic_search`, `ic_clear`, `ic_speaker`, `ic_speaker_slow`, `ic_star`, `ic_star_border`, `ic_more`,
`ic_back`, `ic_history`, `ic_settings`, `ic_info`, `ic_expand`, `ic_collapse`, `bg_badge` (rounded rect shape),
`bg_card` (rounded surface_alt card), `bg_search` (rounded search field), `bg_segment_on`, `bg_segment_off`.
Shared dimens: `gutter` 16dp, `row_pad` 12dp, `corner` 12dp. Themes: `Theme_Rjecnik` (follows system),
`Theme_Rjecnik_Light`, `Theme_Rjecnik_Dark`.
Shared top bar include: `res/layout/topbar.xml` with ids `topbar_back` (ImageButton, gone by default),
`topbar_title` (TextView), `topbar_actions` (LinearLayout for action buttons) — created by resources module.

## Already implemented (do not rewrite; read them before coding)
* `App`, `data/*` (TextNorm, SearchResult, Entry, DictionaryDb, UserStore), `audio/*` (Speech, EspeakPlayer,
  EspeakNative), `ui/Prefs`, `ui/Ui`, `ui/BaseActivity`, `ui/Nav`, `AndroidManifest.xml`, shared resources
  (`values/{colors,dimens,themes,strings}.xml`, `values-night/*`, `drawable/ic_*`, `bg_*`, `layout/topbar.xml`,
  launcher icon).
* Differences from the contracts above:
  - **Every Activity extends `hr.rjecnik.ui.BaseActivity`** (not `Activity`). It applies the theme (light/dark override
    through `applyOverrideConfiguration`) and recreates itself when the theme setting changed. Layouts include the
    top bar with `<include layout="@layout/topbar"/>`; call `setupTopBar(title, showBack)` and
    `addTopBarAction(iconRes, description, listener)` after `setContentView`.
  - **Navigation goes through `hr.rjecnik.ui.Nav`** (`openEntry(ctx,id)`, `openWord(ctx,word)`,
    `openLists(ctx, Nav.TAB_BOOKMARKS|Nav.TAB_HISTORY)`, `openSettings`, `openAbout`, `search(ctx, query)`), and the
    intent extras are `Nav.EXTRA_ID` (long), `Nav.EXTRA_WORD` (String), `Nav.EXTRA_TAB` (String). Never reference
    another screen's Activity class directly.
  - `App.get().db()` blocks on first use (copies ~50 MB from the APK). Always call it from `App.get().io()` and post
    results back with `App.get().main()` / `runOnUiThread`. `App.get().dbReady()` tells whether it is already open.
  - `Speech.speak(text, lang)` and `Speech.speak(text, lang, rateFactor)` (use 0.6 for the slow button);
    speak headwords of `kaj`/`cak` entries and Kajkavian sentences with `Speech.LANG_KAJ`, English with `LANG_EN`.
  - `Prefs.setVoiceEngine/setSpeechRate` also update the live Speech object.
  - Colours: `Ui.color(ctx, R.color.x)`. Theme switching: `Prefs.setTheme(ctx, t)` then `recreate()`.
* Java language level is **8** (lambdas OK; no `var`, no records, no switch expressions, no `List.of`).
  Only framework APIs available on API 24 unless guarded by `Build.VERSION.SDK_INT`.
* Resource naming per screen module (so modules never clash): layouts/drawables `main_*` (MainActivity,
  ResultsAdapter), `lists_*`, `entry_*`, `settings_*`, `about_*`; strings in `values/strings_<module>.xml` with
  names prefixed `<module>_`. `main_lookup_label` already exists in `values/strings.xml`.
* Compile check: `MODULE=<module> bash tools/check_java.sh <your .java files>` compiles the core plus your files
  with only shared + your module's resources. It must print `CHECK OK`.
