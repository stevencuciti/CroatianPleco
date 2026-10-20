package hr.rjecnik.audio;

import android.content.Context;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;
import android.util.Log;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Pronunciation playback. Uses an offline Croatian (or English) voice of the phone's text-to-speech engine when
 * one is installed, and falls back to the built-in eSpeak NG voice otherwise, or when the system engine fails.
 */
public final class Speech {
    public static final int LANG_HR = 0, LANG_KAJ = 1, LANG_EN = 2;
    public static final int ENGINE_AUTO = 0, ENGINE_SYSTEM = 1, ENGINE_ESPEAK = 2;

    public interface Listener {
        void onSpeechStateChanged();
    }

    private static final Locale HR = new Locale("hr", "HR");
    private static final String GOOGLE_TTS = "com.google.android.tts";

    private final Context app;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final EspeakPlayer espeak;
    private final Deque<String> enginesToTry = new ArrayDeque<>();

    private volatile int engine = ENGINE_AUTO;
    private volatile float rate = 1f;
    private volatile Listener listener;

    // System engines; hrTts/enTts point at whichever instance has a usable offline voice.
    private TextToSpeech defaultTts, extraTts;
    private String defaultEngineName, extraEngineName;
    private volatile TextToSpeech hrTts, enTts;
    private volatile Voice hrVoice, enVoice;
    private volatile String hrEngineName;
    private volatile boolean systemInitDone;

    private volatile int utterance;
    private volatile String pendingText;
    private volatile int pendingLang;

    public Speech(Context ctx) {
        app = ctx.getApplicationContext();
        espeak = new EspeakPlayer(app);
        try {
            defaultTts = new TextToSpeech(app, status -> onInit(defaultTts, status, true));
        } catch (Throwable t) {
            systemInitDone = true;
        }
    }

    public void setListener(Listener l) {
        listener = l;
    }

    public void setEngine(int engine) {
        this.engine = engine;
        notifyChanged();
    }

    public void setRate(float rate) {
        this.rate = Math.max(0.3f, Math.min(2f, rate));
    }

    public boolean systemCroatianAvailable() {
        return hrTts != null;
    }

    public void speak(String text, int lang) {
        speak(text, lang, 1f);
    }

    /** Speaks {@code text}; rateFactor multiplies the user's speed setting (e.g. 0.6 for the slow button). */
    public void speak(String text, int lang, float rateFactor) {
        if (text == null || text.trim().isEmpty()) return;
        stop();
        final String t = text.trim();
        final float r = rate * rateFactor;
        TextToSpeech tts = lang == LANG_EN ? enTts : hrTts;
        Voice voice = lang == LANG_EN ? enVoice : hrVoice;
        boolean system = engine != ENGINE_ESPEAK && tts != null;
        if (engine == ENGINE_AUTO && lang == LANG_EN && tts == null) system = false;
        Log.i("Speech", "speak lang=" + lang + " engine=" + (system ? "system " + (voice != null ? voice.getName() : "locale") : "espeak"));
        if (system) {
            try {
                if (voice != null) {
                    tts.setVoice(voice);
                } else {
                    tts.setLanguage(lang == LANG_EN ? Locale.UK : HR);
                }
                tts.setSpeechRate(r);
                String id = "u" + (++utterance);
                pendingText = t;
                pendingLang = lang;
                pendingRate = r;
                Bundle params = new Bundle();
                // Ask for on-device synthesis so the app stays offline even when the engine could use a server.
                params.putString(TextToSpeech.Engine.KEY_FEATURE_EMBEDDED_SYNTHESIS, "true");
                params.putString(TextToSpeech.Engine.KEY_FEATURE_NETWORK_SYNTHESIS, "false");
                if (tts.speak(t, TextToSpeech.QUEUE_FLUSH, params, id) == TextToSpeech.SUCCESS) return;
            } catch (RuntimeException ignored) {
                // fall through to eSpeak
            }
        }
        espeak.speak(t, lang == LANG_EN ? "en-gb" : "hr", r);
    }

    private volatile float pendingRate = 1f;

    public void stop() {
        utterance++;
        espeak.stop();
        try {
            if (hrTts != null) hrTts.stop();
            if (enTts != null && enTts != hrTts) enTts.stop();
        } catch (RuntimeException ignored) {
        }
    }

    public String describeStatus() {
        StringBuilder b = new StringBuilder();
        if (hrTts != null) {
            b.append("Phone voice: Croatian");
            if (hrVoice != null) b.append(" (").append(hrVoice.getName()).append(')');
            if (hrEngineName != null) b.append(" via ").append(engineLabel(hrEngineName));
            b.append(", offline.");
        } else if (!systemInitDone) {
            b.append("Checking the phone's voices…");
        } else {
            b.append("No offline Croatian phone voice found.");
        }
        b.append('\n');
        if (EspeakNative.LOADED) {
            b.append("Built-in eSpeak NG voice: available (always offline, sounds robotic).");
        } else {
            b.append("Built-in eSpeak NG voice: not supported on this device.");
        }
        b.append('\n');
        int e = engine;
        if (e == ENGINE_ESPEAK || (hrTts == null)) {
            b.append("Croatian and Kajkavian are spoken with eSpeak NG.");
        } else {
            b.append("Croatian and Kajkavian are spoken with the phone voice.");
        }
        return b.toString();
    }

    public void shutdown() {
        stop();
        try {
            if (defaultTts != null) defaultTts.shutdown();
            if (extraTts != null) extraTts.shutdown();
        } catch (RuntimeException ignored) {
        }
    }

    // ------------------------------------------------------------------ system TTS discovery

    private void onInit(TextToSpeech tts, int status, boolean isDefault) {
        if (tts == null) {
            // The constructor callback can arrive before the field assignment on some engines; retry shortly.
            main.postDelayed(() -> onInit(isDefault ? defaultTts : extraTts, status, isDefault), 50);
            return;
        }
        if (status == TextToSpeech.SUCCESS) {
            tts.setOnUtteranceProgressListener(progress);
            String engineName = isDefault ? safeDefaultEngine(tts) : extraEngineName;
            if (isDefault) defaultEngineName = engineName;
            scan(tts, engineName);
            if (isDefault && hrTts == null) {
                try {
                    List<TextToSpeech.EngineInfo> engines = tts.getEngines();
                    for (TextToSpeech.EngineInfo info : engines) {
                        if (info.name.equals(defaultEngineName)) continue;
                        if (GOOGLE_TTS.equals(info.name)) enginesToTry.addFirst(info.name);
                        else enginesToTry.addLast(info.name);
                    }
                } catch (RuntimeException ignored) {
                }
            }
        }
        if (!isDefault && hrTts != extraTts && enTts != extraTts && extraTts != null) {
            try {
                extraTts.shutdown();
            } catch (RuntimeException ignored) {
            }
            extraTts = null;
        }
        if (hrTts == null && !enginesToTry.isEmpty()) {
            extraEngineName = enginesToTry.pollFirst();
            try {
                extraTts = new TextToSpeech(app, s -> onInit(extraTts, s, false), extraEngineName);
                return;
            } catch (Throwable ignored) {
                // try the next one on a later call
            }
        }
        systemInitDone = true;
        notifyChanged();
    }

    private static String safeDefaultEngine(TextToSpeech tts) {
        try {
            return tts.getDefaultEngine();
        } catch (RuntimeException e) {
            return null;
        }
    }

    private void scan(TextToSpeech tts, String engineName) {
        Voice bestHr = null, bestBs = null, bestEn = null;
        try {
            Set<Voice> voices = tts.getVoices();
            if (voices != null) {
                for (Voice v : voices) {
                    if (v == null || v.getLocale() == null) continue;
                    if (!isOfflineVoice(v)) continue;
                    String lang = v.getLocale().getLanguage();
                    if ("hr".equals(lang) || "hrv".equals(lang)) {
                        bestHr = better(bestHr, v);
                    } else if ("bs".equals(lang) || "bos".equals(lang)) {
                        bestBs = better(bestBs, v);
                    } else if ("en".equals(lang) || "eng".equals(lang)) {
                        if (bestEn == null || preferEnglish(v, bestEn)) bestEn = v;
                    }
                }
            }
        } catch (RuntimeException ignored) {
        }
        if (bestHr == null) bestHr = bestBs;
        Log.i("Speech", "engine " + engineName + ": offline hr=" + (bestHr != null ? bestHr.getName() : "none") + " en=" + (bestEn != null ? bestEn.getName() : "none"));
        if (hrTts == null) {
            if (bestHr != null) {
                hrVoice = bestHr;
                hrTts = tts;
                hrEngineName = engineName;
            } else if (localeInstalled(tts, HR)) {
                hrVoice = null;
                hrTts = tts;
                hrEngineName = engineName;
            }
        }
        if (enTts == null && bestEn != null) {
            enVoice = bestEn;
            enTts = tts;
        }
    }

    /** Installed on the device and usable without a network connection. */
    private static boolean isOfflineVoice(Voice v) {
        if (v.isNetworkConnectionRequired()) return false;
        Set<String> f = v.getFeatures();
        if (f == null) return true;
        if (f.contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED)) return false;
        // Some engines report a language-level voice that only works through their server.
        return !(f.contains(TextToSpeech.Engine.KEY_FEATURE_NETWORK_SYNTHESIS)
                && !f.contains(TextToSpeech.Engine.KEY_FEATURE_EMBEDDED_SYNTHESIS));
    }

    /** Legacy engines without a voice list: accept the locale only if it is explicitly available offline. */
    @SuppressWarnings("deprecation")
    private static boolean localeInstalled(TextToSpeech tts, Locale loc) {
        try {
            int r = tts.isLanguageAvailable(loc);
            if (r < TextToSpeech.LANG_AVAILABLE) return false;
            Set<String> f = tts.getFeatures(loc);
            return f != null && f.contains(TextToSpeech.Engine.KEY_FEATURE_EMBEDDED_SYNTHESIS)
                    && !f.contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED);
        } catch (RuntimeException e) {
            return false;
        }
    }

    private static Voice better(Voice a, Voice b) {
        if (a == null) return b;
        return b.getQuality() > a.getQuality() ? b : a;
    }

    private static boolean preferEnglish(Voice v, Voice current) {
        int sv = englishRank(v), sc = englishRank(current);
        if (sv != sc) return sv > sc;
        return v.getQuality() > current.getQuality();
    }

    private static int englishRank(Voice v) {
        String c = v.getLocale().getCountry();
        return "GB".equals(c) ? 3 : "US".equals(c) ? 2 : 1;
    }

    private static String engineLabel(String pkg) {
        if (GOOGLE_TTS.equals(pkg)) return "Google";
        if (pkg.contains("samsung")) return "Samsung";
        return pkg;
    }

    private void notifyChanged() {
        final Listener l = listener;
        if (l != null) main.post(l::onSpeechStateChanged);
    }

    private final UtteranceProgressListener progress = new UtteranceProgressListener() {
        @Override
        public void onStart(String utteranceId) {
        }

        @Override
        public void onDone(String utteranceId) {
        }

        @Override
        @SuppressWarnings("deprecation")
        public void onError(String utteranceId) {
            fallback(utteranceId);
        }

        @Override
        public void onError(String utteranceId, int errorCode) {
            fallback(utteranceId);
        }

        private void fallback(String utteranceId) {
            // The system voice failed (e.g. needs a network download): replay this utterance with eSpeak.
            if (!("u" + utterance).equals(utteranceId) || pendingText == null) return;
            espeak.speak(pendingText, pendingLang == LANG_EN ? "en-gb" : "hr", pendingRate);
        }
    };
}
