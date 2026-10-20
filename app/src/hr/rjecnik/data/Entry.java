package hr.rjecnik.data;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.zip.DataFormatException;
import java.util.zip.Inflater;

/** A full dictionary entry, parsed from the deflated JSON blob in entries.data (see docs/APP_SPEC.md). */
public final class Entry {
    public static final class Example {
        public final String text, english, ref, source;

        Example(String text, String english, String ref, String source) {
            this.text = text;
            this.english = english;
            this.ref = ref;
            this.source = source;
        }
    }

    public static final class Sense {
        public final String gloss, labels;
        public final List<Example> examples;
        public final List<String> synonyms, antonyms, see;

        Sense(String gloss, String labels, List<Example> examples, List<String> synonyms, List<String> antonyms,
              List<String> see) {
            this.gloss = gloss;
            this.labels = labels;
            this.examples = examples;
            this.synonyms = synonyms;
            this.antonyms = antonyms;
            this.see = see;
        }
    }

    public static final class Kajkavian {
        public final String words, note, confidence, source;
        /** May be null. */
        public final Example example;

        Kajkavian(String words, String note, String confidence, String source, Example example) {
            this.words = words;
            this.note = note;
            this.confidence = confidence;
            this.source = source;
            this.example = example;
        }
    }

    public static final class Table {
        public final String title;
        public final List<String> cols;
        public final List<List<String>> rows;

        Table(String title, List<String> cols, List<List<String>> rows) {
            this.title = title;
            this.cols = cols;
            this.rows = rows;
        }
    }

    public static final class Form {
        public final String form, label;

        Form(String form, String label) {
            this.form = form;
            this.label = label;
        }
    }

    public final long id;
    public final String headword, accented, pos, gram, dialect, ipa, hyphenation, etymology, standard;
    public final int freq;
    public final List<Sense> senses;
    public final List<Example> aiExamples;
    /** Null if none. */
    public final Kajkavian kajkavian;
    public final List<String> wiktKajkavian;
    public final List<Table> tables;
    public final List<Form> alternatives;
    public final LinkedHashMap<String, List<String>> related;
    public final List<String> synonyms, antonyms, derived, relatedWords;

    private Entry(long id, int freq, JSONObject o) {
        this.id = id;
        this.freq = freq;
        headword = o.optString("w", "");
        accented = o.optString("a", headword);
        pos = o.optString("p", "");
        gram = o.optString("g", "");
        dialect = o.optString("d", "std");
        ipa = o.optString("ipa", "");
        hyphenation = o.optString("hy", "");
        etymology = o.optString("ety", "");
        standard = o.optString("std", "");

        List<Sense> ss = new ArrayList<>();
        JSONArray sa = o.optJSONArray("s");
        if (sa != null) {
            for (int i = 0; i < sa.length(); i++) {
                JSONObject s = sa.optJSONObject(i);
                if (s == null) continue;
                ss.add(new Sense(s.optString("g", ""), s.optString("l", ""), examples(s.optJSONArray("ex"), "wikt"),
                        strings(s.optJSONArray("syn")), strings(s.optJSONArray("ant")), strings(s.optJSONArray("see"))));
            }
        }
        senses = Collections.unmodifiableList(ss);
        aiExamples = examples(o.optJSONArray("ax"), "ai");

        JSONObject k = o.optJSONObject("k");
        if (k != null && !k.optString("w", "").isEmpty()) {
            JSONObject kex = k.optJSONObject("ex");
            Example ex = kex == null || kex.optString("t", "").isEmpty() ? null
                    : new Example(kex.optString("t", ""), kex.optString("en", ""), "", "ai");
            kajkavian = new Kajkavian(k.optString("w", ""), k.optString("n", ""), k.optString("c", "m"),
                    k.optString("src", "ai"), ex);
        } else {
            kajkavian = null;
        }
        wiktKajkavian = strings(o.optJSONArray("kw"));

        List<Table> ts = new ArrayList<>();
        JSONArray ta = o.optJSONArray("t");
        if (ta != null) {
            for (int i = 0; i < ta.length(); i++) {
                JSONObject t = ta.optJSONObject(i);
                if (t == null) continue;
                List<List<String>> rows = new ArrayList<>();
                JSONArray ra = t.optJSONArray("rows");
                if (ra != null) {
                    for (int r = 0; r < ra.length(); r++) rows.add(strings(ra.optJSONArray(r)));
                }
                ts.add(new Table(t.optString("title", ""), strings(t.optJSONArray("cols")), rows));
            }
        }
        tables = Collections.unmodifiableList(ts);

        List<Form> fs = new ArrayList<>();
        JSONArray fa = o.optJSONArray("alt");
        if (fa != null) {
            for (int i = 0; i < fa.length(); i++) {
                JSONObject f = fa.optJSONObject(i);
                if (f != null && !f.optString("form", "").isEmpty()) {
                    fs.add(new Form(f.optString("form", ""), f.optString("label", "")));
                }
            }
        }
        alternatives = Collections.unmodifiableList(fs);

        related = new LinkedHashMap<>();
        JSONObject rel = o.optJSONObject("rel");
        if (rel != null) {
            Iterator<String> it = rel.keys();
            while (it.hasNext()) {
                String key = it.next();
                List<String> words = strings(rel.optJSONArray(key));
                if (!words.isEmpty()) related.put(key, words);
            }
        }
        synonyms = strings(o.optJSONArray("syn"));
        antonyms = strings(o.optJSONArray("ant"));
        derived = strings(o.optJSONArray("der"));
        relatedWords = strings(o.optJSONArray("relw"));
    }

    /** True if any AI-generated content is present. */
    public boolean hasAiContent() {
        return !aiExamples.isEmpty() || (kajkavian != null && "ai".equals(kajkavian.source)) || !standard.isEmpty();
    }

    public static Entry parse(long id, int freq, byte[] deflatedJson) throws JSONException, DataFormatException {
        return new Entry(id, freq, new JSONObject(inflate(deflatedJson)));
    }

    static String inflate(byte[] data) throws DataFormatException {
        Inflater inf = new Inflater();
        try {
            inf.setInput(data);
            ByteArrayOutputStream out = new ByteArrayOutputStream(data.length * 4);
            byte[] buf = new byte[8192];
            while (!inf.finished()) {
                int n = inf.inflate(buf);
                if (n == 0 && (inf.needsInput() || inf.needsDictionary())) break;
                out.write(buf, 0, n);
            }
            return new String(out.toByteArray(), StandardCharsets.UTF_8);
        } finally {
            inf.end();
        }
    }

    private static List<String> strings(JSONArray a) {
        if (a == null || a.length() == 0) return Collections.emptyList();
        List<String> out = new ArrayList<>(a.length());
        for (int i = 0; i < a.length(); i++) {
            String s = a.optString(i, "");
            if (s != null) out.add(s);
        }
        return Collections.unmodifiableList(out);
    }

    private static List<Example> examples(JSONArray a, String defaultSource) {
        if (a == null || a.length() == 0) return Collections.emptyList();
        List<Example> out = new ArrayList<>(a.length());
        for (int i = 0; i < a.length(); i++) {
            JSONObject e = a.optJSONObject(i);
            if (e == null || e.optString("hr", "").isEmpty()) continue;
            out.add(new Example(e.optString("hr", ""), e.optString("en", ""), e.optString("ref", ""),
                    e.optString("src", defaultSource)));
        }
        return Collections.unmodifiableList(out);
    }
}
