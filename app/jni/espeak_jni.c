/*
 * Minimal JNI bridge to eSpeak NG (GPLv3) used as the always-available offline voice.
 * Java side: hr.rjecnik.audio.EspeakNative. All calls are serialised by the Java class.
 */
#include <jni.h>
#include <stdlib.h>
#include <string.h>
#include <android/log.h>
#include <espeak-ng/speak_lib.h>

#define TAG "hrspeak"

static short *g_buf = NULL;
static size_t g_len = 0;
static size_t g_cap = 0;
static int g_ready = 0;

static int synth_callback(short *wav, int numsamples, espeak_EVENT *events) {
    (void) events;
    if (wav == NULL || numsamples <= 0) return 0;
    if (g_len + (size_t) numsamples > g_cap) {
        size_t cap = g_cap ? g_cap : 22050;
        while (cap < g_len + (size_t) numsamples) cap *= 2;
        short *nb = (short *) realloc(g_buf, cap * sizeof(short));
        if (nb == NULL) return 1; /* abort synthesis */
        g_buf = nb;
        g_cap = cap;
    }
    memcpy(g_buf + g_len, wav, (size_t) numsamples * sizeof(short));
    g_len += (size_t) numsamples;
    return 0;
}

JNIEXPORT jint JNICALL
Java_hr_rjecnik_audio_EspeakNative_nativeInit(JNIEnv *env, jclass clazz, jstring dataParent) {
    (void) clazz;
    const char *path = (*env)->GetStringUTFChars(env, dataParent, NULL);
    int rate = espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, path, espeakINITIALIZE_DONT_EXIT);
    (*env)->ReleaseStringUTFChars(env, dataParent, path);
    if (rate <= 0) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "espeak_Initialize failed: %d", rate);
        return -1;
    }
    espeak_SetSynthCallback(synth_callback);
    g_ready = 1;
    return rate;
}

JNIEXPORT jboolean JNICALL
Java_hr_rjecnik_audio_EspeakNative_nativeSetVoice(JNIEnv *env, jclass clazz, jstring name) {
    (void) clazz;
    if (!g_ready) return JNI_FALSE;
    const char *n = (*env)->GetStringUTFChars(env, name, NULL);
    espeak_ERROR err = espeak_SetVoiceByName(n);
    (*env)->ReleaseStringUTFChars(env, name, n);
    return err == EE_OK ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jshortArray JNICALL
Java_hr_rjecnik_audio_EspeakNative_nativeSynth(JNIEnv *env, jclass clazz, jstring text, jint rate, jint pitch) {
    (void) clazz;
    if (!g_ready) return NULL;
    const char *t = (*env)->GetStringUTFChars(env, text, NULL);
    g_len = 0;
    espeak_SetParameter(espeakRATE, rate, 0);
    espeak_SetParameter(espeakPITCH, pitch, 0);
    espeak_ERROR err = espeak_Synth(t, strlen(t) + 1, 0, POS_CHARACTER, 0, espeakCHARS_UTF8, NULL, NULL);
    if (err == EE_OK) espeak_Synchronize();
    (*env)->ReleaseStringUTFChars(env, text, t);
    if (err != EE_OK) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "espeak_Synth failed: %d", err);
        return NULL;
    }
    jshortArray out = (*env)->NewShortArray(env, (jsize) g_len);
    if (out != NULL && g_len > 0) (*env)->SetShortArrayRegion(env, out, 0, (jsize) g_len, g_buf);
    return out;
}
