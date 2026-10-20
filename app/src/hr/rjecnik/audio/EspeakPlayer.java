package hr.rjecnik.audio;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.res.AssetManager;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioTrack;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Log;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

/** Built-in offline voice: synthesises with eSpeak NG on a worker thread and plays the PCM with AudioTrack. */
public final class EspeakPlayer {
    private static final String TAG = "EspeakPlayer";
    private static final String ASSET_DIR = "espeak-ng-data";

    private final Context app;
    private final Handler worker;
    private final Object trackLock = new Object();
    private volatile int generation;
    private AudioTrack track;
    private boolean initTried, initOk;
    private int sampleRate = 22050;
    private String currentVoice;

    public EspeakPlayer(Context ctx) {
        app = ctx.getApplicationContext();
        HandlerThread t = new HandlerThread("espeak");
        t.start();
        worker = new Handler(t.getLooper());
    }

    /** False if the native library could not be loaded on this device. */
    public boolean available() {
        return EspeakNative.LOADED && (!initTried || initOk);
    }

    /** @param voice eSpeak voice name, e.g. "hr" or "en-gb"; rate 1.0 = normal speed. */
    public void speak(final String text, final String voice, final float rate) {
        final int gen = ++generation;
        stopTrack();
        worker.post(() -> {
            if (gen != generation || !ensureInit()) return;
            if (!voice.equals(currentVoice)) {
                boolean ok = EspeakNative.nativeSetVoice(voice);
                if (!ok && voice.startsWith("en")) ok = EspeakNative.nativeSetVoice("en");
                currentVoice = ok ? voice : null;
                if (!ok) return;
            }
            int wpm = Math.max(80, Math.min(400, Math.round(165 * rate)));
            short[] pcm = EspeakNative.nativeSynth(text, wpm, 50);
            Log.i(TAG, "synthesised " + (pcm == null ? -1 : pcm.length) + " samples (" + voice + ")");
            if (gen != generation || pcm == null || pcm.length == 0) return;
            play(pcm, gen);
        });
    }

    public void stop() {
        generation++;
        stopTrack();
    }

    private boolean ensureInit() {
        if (initTried) return initOk;
        initTried = true;
        if (!EspeakNative.LOADED) return false;
        try {
            File parent = new File(app.getNoBackupFilesDir(), "espeak");
            installData(parent);
            int rate = EspeakNative.nativeInit(parent.getAbsolutePath());
            if (rate > 0) {
                sampleRate = rate;
                initOk = true;
            }
            Log.i(TAG, "eSpeak init: sample rate " + rate);
        } catch (Throwable t) {
            Log.e(TAG, "eSpeak init failed", t);
        }
        return initOk;
    }

    private void installData(File parent) throws IOException {
        File stampFile = new File(parent, ".stamp");
        String stamp;
        try {
            PackageInfo pi = app.getPackageManager().getPackageInfo(app.getPackageName(), 0);
            stamp = pi.lastUpdateTime + "";
        } catch (Exception e) {
            stamp = "0";
        }
        if (stampFile.exists() && stamp.equals(readSmall(stampFile))) return;
        copyAssetTree(app.getAssets(), ASSET_DIR, new File(parent, ASSET_DIR));
        try (OutputStream out = new FileOutputStream(stampFile)) {
            out.write(stamp.getBytes(StandardCharsets.UTF_8));
        }
    }

    private static void copyAssetTree(AssetManager am, String path, File dest) throws IOException {
        String[] children = am.list(path);
        if (children == null || children.length == 0) {
            File parentDir = dest.getParentFile();
            if (parentDir != null && !parentDir.isDirectory() && !parentDir.mkdirs()) {
                throw new IOException("mkdir " + parentDir);
            }
            try (InputStream in = am.open(path); OutputStream out = new FileOutputStream(dest)) {
                byte[] buf = new byte[1 << 15];
                int n;
                while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            }
            return;
        }
        if (!dest.isDirectory() && !dest.mkdirs()) throw new IOException("mkdir " + dest);
        for (String child : children) copyAssetTree(am, path + "/" + child, new File(dest, child));
    }

    private static String readSmall(File f) {
        try (InputStream in = new FileInputStream(f)) {
            byte[] b = new byte[64];
            int n = in.read(b);
            return n > 0 ? new String(b, 0, n, StandardCharsets.UTF_8) : "";
        } catch (IOException e) {
            return "";
        }
    }

    private void play(short[] pcm, int gen) {
        synchronized (trackLock) {
            if (gen != generation) return;
            releaseTrackLocked();
            try {
                AudioTrack t = new AudioTrack.Builder()
                        .setAudioAttributes(new AudioAttributes.Builder()
                                .setUsage(AudioAttributes.USAGE_MEDIA)
                                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                                .build())
                        .setAudioFormat(new AudioFormat.Builder()
                                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                                .setSampleRate(sampleRate)
                                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                                .build())
                        .setTransferMode(AudioTrack.MODE_STATIC)
                        .setBufferSizeInBytes(pcm.length * 2)
                        .build();
                t.write(pcm, 0, pcm.length);
                t.setNotificationMarkerPosition(pcm.length);
                t.setPlaybackPositionUpdateListener(new AudioTrack.OnPlaybackPositionUpdateListener() {
                    @Override
                    public void onMarkerReached(AudioTrack at) {
                        synchronized (trackLock) {
                            if (track == at) releaseTrackLocked();
                        }
                    }

                    @Override
                    public void onPeriodicNotification(AudioTrack at) {
                    }
                }, worker);
                track = t;
                t.play();
            } catch (Exception e) {
                Log.e(TAG, "playback failed", e);
                releaseTrackLocked();
            }
        }
    }

    private void stopTrack() {
        synchronized (trackLock) {
            releaseTrackLocked();
        }
    }

    private void releaseTrackLocked() {
        if (track != null) {
            try {
                track.stop();
            } catch (IllegalStateException ignored) {
            }
            track.release();
            track = null;
        }
    }
}
