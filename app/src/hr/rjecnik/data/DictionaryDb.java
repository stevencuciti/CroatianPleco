package hr.rjecnik.data;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Read-only access to the bundled offline dictionary (assets/dict.db). Thread-safe. */
public final class DictionaryDb {
    public static final int MODE_AUTO = 0, MODE_HR = 1, MODE_EN = 2;

    private static final String ASSET = "dict.db";
    private static final String PREFS = "dictionary_db";

    private final SQLiteDatabase db;

    private DictionaryDb(SQLiteDatabase db) {
        this.db = db;
    }

    /** Copies the database out of the APK when missing or after an app update, then opens it read-only. */
    public static DictionaryDb open(Context ctx) throws IOException {
        Context app = ctx.getApplicationContext();
        File file = new File(app.getNoBackupFilesDir(), ASSET);
        String stamp = installStamp(app);
        SharedPreferences sp = app.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        if (!file.exists() || !stamp.equals(sp.getString("installed", ""))) {
            copyAsset(app, file);
            sp.edit().putString("installed", stamp).commit();
        }
        SQLiteDatabase sql;
        try {
            sql = SQLiteDatabase.openDatabase(file.getPath(), null,
                    SQLiteDatabase.OPEN_READONLY | SQLiteDatabase.NO_LOCALIZED_COLLATORS);
        } catch (RuntimeException e) {
            // Corrupt or partial copy: copy again once.
            copyAsset(app, file);
            sql = SQLiteDatabase.openDatabase(file.getPath(), null,
                    SQLiteDatabase.OPEN_READONLY | SQLiteDatabase.NO_LOCALIZED_COLLATORS);
        }
        return new DictionaryDb(sql);
    }

    private static String installStamp(Context app) {
        try {
            PackageInfo pi = app.getPackageManager().getPackageInfo(app.getPackageName(), 0);
            @SuppressWarnings("deprecation") long code = pi.versionCode;
            return code + ":" + pi.lastUpdateTime;
        } catch (PackageManager.NameNotFoundException e) {
            return "0";
        }
    }

    private static void copyAsset(Context app, File dest) throws IOException {
        File tmp = new File(dest.getPath() + ".tmp");
        try (InputStream in = app.getAssets().open(ASSET); OutputStream out = new FileOutputStream(tmp)) {
            byte[] buf = new byte[1 << 16];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        }
        if (dest.exists() && !dest.delete()) throw new IOException("Cannot replace " + dest);
        if (!tmp.renameTo(dest)) throw new IOException("Cannot rename " + tmp);
    }

    // ------------------------------------------------------------------ search

    private static final class Hit {
        long id;
        int score;
        int type;
        String form, info;
    }

    public List<SearchResult> search(String query, int mode, int limit) {
        if (query == null) return Collections.emptyList();
        String q = query.trim();
        if (q.isEmpty()) return Collections.emptyList();
        String qf = TextNorm.fold(q);
        String qe = TextNorm.enNorm(q);
        Map<Long, Hit> hits = new HashMap<>();

        if ((mode == MODE_AUTO || mode == MODE_HR) && !qf.isEmpty()) {
            try (Cursor c = db.rawQuery("SELECT entry_id, kind, form, info FROM hr_index WHERE term = ? LIMIT 300",
                    new String[]{qf})) {
                while (c.moveToNext()) {
                    int kind = c.getInt(1);
                    int score = kind == 0 ? 1000 : kind == 1 ? 920 : kind == 2 ? 860 : 820;
                    int type = kind == 0 ? SearchResult.MATCH_HR_HEAD : kind == 1 ? SearchResult.MATCH_KAJ
                            : kind == 2 ? SearchResult.MATCH_HR_FORM : SearchResult.MATCH_ALT;
                    offer(hits, c.getLong(0), score, type, kind == 0 ? null : c.getString(2),
                            kind == 0 ? null : c.getString(3));
                }
            }
            try (Cursor c = db.rawQuery("SELECT entry_id, kind, term, form FROM hr_index WHERE term > ? AND term < ? "
                    + "AND kind IN (0,1) ORDER BY term LIMIT 400", new String[]{qf, qf + "￿"})) {
                while (c.moveToNext()) {
                    int kind = c.getInt(1);
                    int extra = c.getString(2).length() - qf.length();
                    int score = Math.max(300, 600 - 4 * extra);
                    offer(hits, c.getLong(0), score, kind == 1 ? SearchResult.MATCH_KAJ : SearchResult.MATCH_HR_PREFIX,
                            kind == 1 ? c.getString(3) : null, kind == 1 ? "Međimurje Kajkavian" : null);
                }
            }
        }

        if ((mode == MODE_AUTO || mode == MODE_EN) && !qe.isEmpty()) {
            int penalty = mode == MODE_AUTO && TextNorm.hasCroatianLetters(q) ? 400 : 0;
            try (Cursor c = db.rawQuery("SELECT entry_id, weight FROM en_index WHERE term = ? ORDER BY weight DESC LIMIT 400",
                    new String[]{qe})) {
                while (c.moveToNext()) {
                    int score = 300 + (int) (c.getInt(1) * 0.7f) - penalty;
                    offer(hits, c.getLong(0), score, SearchResult.MATCH_EN, null, null);
                }
            }
            if (qe.length() >= 2) {
                try (Cursor c = db.rawQuery("SELECT entry_id, weight FROM en_index WHERE term > ? AND term < ? "
                        + "ORDER BY weight DESC LIMIT 300", new String[]{qe, qe + "￿"})) {
                    while (c.moveToNext()) {
                        int score = 200 + (int) (c.getInt(1) * 0.35f) - penalty;
                        offer(hits, c.getLong(0), score, SearchResult.MATCH_EN_PREFIX, null, null);
                    }
                }
            }
        }
        if (hits.isEmpty()) return Collections.emptyList();

        // Load summaries for every candidate, then apply frequency / dialect adjustments and sort.
        Map<Long, String[]> rows = loadSummaries(new ArrayList<>(hits.keySet()));
        // Typed with diacritics and spelled exactly like the headword: prefer it over diacritic-less look-alikes.
        String exact = TextNorm.hasCroatianLetters(q) ? TextNorm.stripAccents(q).toLowerCase(Locale.ROOT) : null;
        List<SearchResult> out = new ArrayList<>(hits.size());
        for (Hit h : hits.values()) {
            String[] r = rows.get(h.id);
            if (r == null) continue;
            int freq = parseInt(r[6], 2);
            int score = h.score + freq * 12;
            if ("name".equals(r[3])) score -= 60;
            if (exact != null && h.type == SearchResult.MATCH_HR_HEAD && exact.equals(r[1].toLowerCase(Locale.ROOT))) {
                score += 40;
            }
            boolean dialectEntry = "kaj".equals(r[5]) || "cak".equals(r[5]);
            if (dialectEntry && h.type != SearchResult.MATCH_HR_HEAD && h.type != SearchResult.MATCH_KAJ
                    && h.type != SearchResult.MATCH_HR_PREFIX) {
                score -= 20;
            }
            out.add(new SearchResult(h.id, r[1], r[2], r[3], r[4], r[5], r[7], r[8], freq, h.type, h.form, h.info, score));
        }
        Collections.sort(out, (a, b) -> {
            if (a.score != b.score) return b.score - a.score;
            if (a.freq != b.freq) return b.freq - a.freq;
            return a.headword.length() - b.headword.length();
        });
        return out.size() > limit ? new ArrayList<>(out.subList(0, limit)) : out;
    }

    private static void offer(Map<Long, Hit> hits, long id, int score, int type, String form, String info) {
        Hit h = hits.get(id);
        if (h == null) {
            h = new Hit();
            h.id = id;
            h.score = Integer.MIN_VALUE;
            hits.put(id, h);
        }
        if (score > h.score) {
            h.score = score;
            h.type = type;
            h.form = form;
            h.info = info;
        }
    }

    private Map<Long, String[]> loadSummaries(List<Long> ids) {
        Map<Long, String[]> out = new HashMap<>(ids.size() * 2);
        final int chunk = 400;
        for (int i = 0; i < ids.size(); i += chunk) {
            List<Long> part = ids.subList(i, Math.min(ids.size(), i + chunk));
            StringBuilder sql = new StringBuilder(
                    "SELECT id, headword, accented, pos, gram, dialect, freq, gloss, kaj FROM entries WHERE id IN (");
            for (int j = 0; j < part.size(); j++) sql.append(j == 0 ? "" : ",").append(part.get(j).longValue());
            sql.append(')');
            try (Cursor c = db.rawQuery(sql.toString(), null)) {
                while (c.moveToNext()) {
                    String[] r = new String[9];
                    for (int k = 0; k < 9; k++) r[k] = c.isNull(k) ? "" : c.getString(k);
                    out.put(c.getLong(0), r);
                }
            }
        }
        return out;
    }

    // ------------------------------------------------------------------ entries

    public Entry getEntry(long id) {
        try (Cursor c = db.rawQuery("SELECT freq, data FROM entries WHERE id = ?", new String[]{String.valueOf(id)})) {
            if (!c.moveToFirst()) return null;
            return Entry.parse(id, c.getInt(0), c.getBlob(1));
        } catch (Exception e) {
            return null;
        }
    }

    /** Exact headword matches (kind 0) for a word, used for cross-reference links. */
    public List<SearchResult> lookupHeadword(String word) {
        String key = TextNorm.fold(TextNorm.stripAccents(word));
        if (key.isEmpty()) return Collections.emptyList();
        List<Long> ids = new ArrayList<>();
        try (Cursor c = db.rawQuery("SELECT DISTINCT entry_id FROM hr_index WHERE term = ? AND kind = 0 LIMIT 20",
                new String[]{key})) {
            while (c.moveToNext()) ids.add(c.getLong(0));
        }
        if (ids.isEmpty()) {
            // fall back to any match (inflected form, Kajkavian, variant)
            return search(word, MODE_HR, 10);
        }
        Map<Long, String[]> rows = loadSummaries(ids);
        String plain = TextNorm.stripAccents(word).trim();
        List<SearchResult> out = new ArrayList<>();
        for (long id : ids) {
            String[] r = rows.get(id);
            if (r == null) continue;
            int freq = parseInt(r[6], 2);
            int score = 1000 + freq * 12 + (r[1].equals(plain) ? 50 : 0);
            out.add(new SearchResult(id, r[1], r[2], r[3], r[4], r[5], r[7], r[8], freq,
                    SearchResult.MATCH_HR_HEAD, null, null, score));
        }
        Collections.sort(out, (a, b) -> b.score - a.score);
        return out;
    }

    /** Deterministic "word of the day": a common standard-Croatian entry chosen by seed. */
    public SearchResult randomCommonEntry(long seed) {
        int count;
        try (Cursor c = db.rawQuery("SELECT COUNT(*) FROM entries WHERE freq >= 4 AND dialect = 'std' AND pos != 'name'",
                null)) {
            count = c.moveToFirst() ? c.getInt(0) : 0;
        }
        String where = count > 0 ? "freq >= 4 AND dialect = 'std' AND pos != 'name'" : "1";
        if (count == 0) {
            try (Cursor c = db.rawQuery("SELECT COUNT(*) FROM entries", null)) {
                count = c.moveToFirst() ? c.getInt(0) : 0;
            }
        }
        if (count == 0) return null;
        long offset = Math.floorMod(seed * 2654435761L, (long) count);
        try (Cursor c = db.rawQuery("SELECT id, headword, accented, pos, gram, dialect, freq, gloss, kaj FROM entries WHERE "
                + where + " ORDER BY id LIMIT 1 OFFSET " + offset, null)) {
            if (!c.moveToFirst()) return null;
            String[] r = new String[9];
            for (int k = 0; k < 9; k++) r[k] = c.isNull(k) ? "" : c.getString(k);
            return new SearchResult(c.getLong(0), r[1], r[2], r[3], r[4], r[5], r[7], r[8], parseInt(r[6], 2),
                    SearchResult.MATCH_HR_HEAD, null, null, 0);
        }
    }

    public String meta(String key) {
        try (Cursor c = db.rawQuery("SELECT value FROM meta WHERE key = ?", new String[]{key})) {
            return c.moveToFirst() ? c.getString(0) : null;
        }
    }

    public int entryCount() {
        try (Cursor c = db.rawQuery("SELECT COUNT(*) FROM entries", null)) {
            return c.moveToFirst() ? c.getInt(0) : 0;
        }
    }

    private static int parseInt(String s, int def) {
        try {
            return Integer.parseInt(s);
        } catch (NumberFormatException e) {
            return def;
        }
    }
}
