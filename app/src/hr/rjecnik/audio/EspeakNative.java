package hr.rjecnik.audio;

/** JNI bindings to libhrspeak.so (eSpeak NG). Implemented in app/jni/espeak_jni.c; not thread-safe. */
final class EspeakNative {
    static final boolean LOADED;

    static {
        boolean ok;
        try {
            System.loadLibrary("hrspeak");
            ok = true;
        } catch (Throwable t) {
            ok = false;
        }
        LOADED = ok;
    }

    private EspeakNative() {
    }

    /** @param dataParentDir directory containing espeak-ng-data/. Returns the sample rate, or a negative value. */
    static native int nativeInit(String dataParentDir);

    static native boolean nativeSetVoice(String name);

    /** Returns mono 16-bit PCM at the sample rate from {@link #nativeInit}, or null on failure. */
    static native short[] nativeSynth(String text, int rateWpm, int pitch0to99);
}
