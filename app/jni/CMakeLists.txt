cmake_minimum_required(VERSION 3.10)
project(hrspeak C)

# Build only the eSpeak NG library itself: no async thread, no MBROLA, no C++ speech-player.
set(USE_ASYNC OFF CACHE BOOL "" FORCE)
set(USE_MBROLA OFF CACHE BOOL "" FORCE)
set(USE_LIBSONIC OFF CACHE BOOL "" FORCE)
set(USE_LIBPCAUDIO OFF CACHE BOOL "" FORCE)
set(USE_SPEECHPLAYER OFF CACHE BOOL "" FORCE)
set(USE_KLATT ON CACHE BOOL "" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)

add_subdirectory(${ESPEAK_SRC} espeakng EXCLUDE_FROM_ALL)

add_library(hrspeak SHARED espeak_jni.c)
target_link_libraries(hrspeak PRIVATE espeak-ng log)
# 16 KB page alignment so the library loads on Android 15+ devices with 16 KB pages.
target_link_options(hrspeak PRIVATE "-Wl,-z,max-page-size=16384" "-Wl,--gc-sections" "-s")
