package hr.rjecnik;

import android.app.Application;
import android.os.Handler;
import android.os.Looper;

import java.io.IOException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import hr.rjecnik.audio.Speech;
import hr.rjecnik.data.DictionaryDb;
import hr.rjecnik.data.UserStore;
import hr.rjecnik.ui.Prefs;

/** Application singleton holding the dictionary, user data, speech engine and shared threads. */
public final class App extends Application {
    private static App instance;

    private final Object dbLock = new Object();
    private DictionaryDb db;
    private UserStore user;
    private Speech speech;
    private ExecutorService io;
    private Handler main;

    public static App get() {
        return instance;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;
        io = Executors.newFixedThreadPool(4);
        main = new Handler(Looper.getMainLooper());
    }

    /**
     * Opens (copying from assets on first run) the dictionary database. Blocks, so call it from {@link #io()};
     * the first call after install can take a few seconds.
     */
    public DictionaryDb db() {
        synchronized (dbLock) {
            if (db == null) {
                try {
                    db = DictionaryDb.open(this);
                } catch (IOException e) {
                    throw new IllegalStateException("Could not open dictionary", e);
                }
            }
            return db;
        }
    }

    /** True once {@link #db()} has completed at least once. */
    public boolean dbReady() {
        synchronized (dbLock) {
            return db != null;
        }
    }

    public synchronized UserStore user() {
        if (user == null) user = new UserStore(this);
        return user;
    }

    public synchronized Speech speech() {
        if (speech == null) {
            speech = new Speech(this);
            speech.setEngine(Prefs.voiceEngine(this));
            speech.setRate(Prefs.speechRate(this));
        }
        return speech;
    }

    public ExecutorService io() {
        return io;
    }

    public Handler main() {
        return main;
    }
}
