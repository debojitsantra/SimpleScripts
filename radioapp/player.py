"""
Core playback engine.
"""
import enum
import os
import random
import socket
import subprocess
import threading
import time
from typing import List, Optional

from radioapp import config
from radioapp.db import Library, Song
from radioapp.transcoder import Transcoder
from radioapp.scrobbler import Scrobbler


class Mode(str, enum.Enum):
    SHUFFLE = "shuffle"
    SORT_NEWEST = "sort_newest"
    SORT_OLDEST = "sort_oldest"


# Size of each chunk read/written while feeding audio into the
# persistent output stream.
_CHUNK_SIZE = 16384


class Player:
    def __init__(self, db: Library, log_fn=print):
        self.db = db
        self.log = log_fn
        self.transcoder = Transcoder()
        self.scrobbler = Scrobbler(log_fn=log_fn)

        self.mode: Mode = Mode.SHUFFLE
        self._queue: List[Song] = []
        self._queue_pos: int = -1

        self._current_song: Optional[Song] = None
        self._play_thread: Optional[threading.Thread] = None

        # The single, long-lived ffmpeg process that owns the Icecast
        self._out_proc: Optional[subprocess.Popen] = None
        self._out_lock = threading.Lock()

        # Per-song live-transcode subprocess (only used when the
        # pre-warmed cache isn't ready in time), kept here so skip()
        # has something to kill immediately.
        self._decode_proc: Optional[subprocess.Popen] = None

        self._stop_flag = threading.Event()
        self._skip_flag = threading.Event()
        self._lock = threading.RLock()
        self._interrupt_song: Optional[Song] = None
        self._running = False

    #Queue

    def _build_queue(self, mode: Mode) -> List[Song]:
        if mode == Mode.SHUFFLE:
            songs = self.db.all_songs()
            random.shuffle(songs)
            return songs
        elif mode == Mode.SORT_NEWEST:
            return self.db.songs_sorted_by_mtime(newest_first=True)
        elif mode == Mode.SORT_OLDEST:
            return self.db.songs_sorted_by_mtime(newest_first=False)
        return []

    def set_mode(self, mode: Mode):
        with self._lock:
            self.mode = mode
            self._queue = self._build_queue(mode)
            self._queue_pos = -1
            self.log(f"[player] mode set to {mode.value}, {len(self._queue)} songs queued")
        self._skip_flag.set()  # jump to new queue immediately

    def play_now(self, song: Song):
        """Play a specific song immediately, then resume current mode."""
        with self._lock:
            self._interrupt_song = song
        self._skip_flag.set()

    def _next_song(self) -> Optional[Song]:
        with self._lock:
            if self._interrupt_song is not None:
                song = self._interrupt_song
                self._interrupt_song = None
                return song

            if not self._queue:
                self._queue = self._build_queue(self.mode)
                self._queue_pos = -1

            self._queue_pos += 1
            if self._queue_pos >= len(self._queue):
                self._queue = self._build_queue(self.mode)
                self._queue_pos = 0

            if not self._queue:
                return None
            return self._queue[self._queue_pos]

    def _peek_next_song(self) -> Optional[Song]:
        with self._lock:
            if self._interrupt_song is not None:
                return None 
            if not self._queue:
                return None
            peek_pos = self._queue_pos + 1
            if peek_pos >= len(self._queue):
                return self._queue[0] if self._queue else None
            return self._queue[peek_pos]

    #playback control

    def current(self) -> Optional[Song]:
        return self._current_song

    def status(self) -> dict:
        with self._lock:
            return {
                "mode": self.mode.value,
                "current": self._current_song.display() if self._current_song else None,
                "queue_pos": self._queue_pos,
                "queue_len": len(self._queue),
            }

    def skip(self):
        self.log("[player] skip requested")
        if self._decode_proc and self._decode_proc.poll() is None:
            self._decode_proc.terminate()
        self._skip_flag.set()

    def start(self):
        if self._running:
            return
        self._running = True
        self._stop_flag.clear()
        with self._lock:
            if not self._queue:
                self._queue = self._build_queue(self.mode)
        self._ensure_output_proc()
        self._play_thread = threading.Thread(target=self._play_loop, daemon=True)
        self._play_thread.start()

    def stop(self):
        self._stop_flag.set()
        self._skip_flag.set()

        if self._decode_proc and self._decode_proc.poll() is None:
            try:
                self._decode_proc.terminate()
                self._decode_proc.wait(timeout=3)
            except Exception:
                try:
                    self._decode_proc.kill()
                except Exception:
                    pass

        with self._out_lock:
            if self._out_proc and self._out_proc.poll() is None:
                try:
                    if self._out_proc.stdin:
                        self._out_proc.stdin.close()
                    self._out_proc.terminate()
                    self._out_proc.wait(timeout=3)
                except Exception:
                    try:
                        self._out_proc.kill()
                    except Exception:
                        pass
            self._out_proc = None

        self._running = False

    #icecast connection

    def _spawn_output_proc(self) -> Optional[subprocess.Popen]:
        cmd = [
            "ffmpeg", "-nostdin", "-re",
            "-f", "s16le", "-acodec", "pcm_s16le",
            "-ar", config.SAMPLE_RATE, "-ac", config.CHANNELS,
            "-i", "pipe:0",
            "-b:a", config.MP3_BITRATE,
            "-f", "mp3",
            config.icecast_url(),
        ]
        self.log(f"[player] output cmd: {' '.join(cmd)}")
        try:
            with open(config.LOG_FILE, "a") as logf:
                proc = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE, stdout=logf, stderr=logf,
                )
            self.log("[player] connected to Icecast")
            return proc
        except FileNotFoundError:
            self.log("[player] ERROR: ffmpeg not found on PATH")
            return None

    def _icecast_reachable(self) -> bool:
   #Quick TCP Probe
        try:
            with socket.create_connection((config.ICECAST_HOST, config.ICECAST_PORT), timeout=1):
                return True
        except OSError:
            return False

    def _ensure_output_proc(self) -> bool:
        """Make sure the persistent Icecast connection is alive, (re)connecting if needed."""
        with self._out_lock:
            if self._out_proc is not None and self._out_proc.poll() is None:
                return True
            if self._out_proc is not None:
                self.log("[player] Icecast connection dropped, reconnecting...")
            if not self._icecast_reachable():
                self._out_proc = None
                return False
            self._out_proc = self._spawn_output_proc()
            return self._out_proc is not None

    def _write_out(self, data: bytes) -> bool:
        with self._out_lock:
            proc = self._out_proc
        if proc is None or proc.stdin is None:
            return False
        try:
            proc.stdin.write(data)
            proc.stdin.flush()
            return True
        except (BrokenPipeError, OSError):
            return False

    #main loop

    def _play_loop(self):
        while not self._stop_flag.is_set():
            try:
                song = self._next_song()
                if song is None:
                    self.log("[player] library empty, retrying in 5s")
                    time.sleep(5)
                    continue

                self._current_song = song
                self.log(f"[player] Now playing: {song.display()}  ({song.quality_dir})")

                self.scrobbler.now_playing_async(song.artist, song.title, song.album)


                upcoming = self._peek_next_song()
                if upcoming is not None and config.needs_transcoding(upcoming.path):
                    self.transcoder.start_preload(upcoming.path)

                if not self._ensure_output_proc():
                    self.log("[player] could not connect to Icecast, retrying in 3s")
                    time.sleep(3)
                    continue

                played_start = time.time()
                self._stream_song(song)
                played_secs = time.time() - played_start
                # Only scrobble if it was actually listened to, per Last.fm's own rule
                dur = song.duration
                threshold = min(dur / 2, 240) if dur else 30
                if played_secs >= 30 and played_secs >= threshold:
                    self.scrobbler.scrobble_async(song.artist, song.title, song.album)

                # Cache hygiene (only meaningful for paths that actually
                # get transcoded; harmless no-op otherwise)
                keep = {song.path}
                if upcoming:
                    keep.add(upcoming.path)
                if config.TRANSCODING_ENABLED:
                    self.transcoder.cleanup_cache(keep_paths=keep, max_files=5)

                self._skip_flag.clear()
            except Exception as e:
                self.log(f"[player] ERROR in play loop: {e}")
                time.sleep(1)

        self.log("[player] playback loop stopped")

    def _stream_song(self, song: Song):
        source_path = song.path

        if config.needs_transcoding(song.path):
            if not self.transcoder.is_cached(song.path):
                self.transcoder.wait_for(song.path, timeout=1.5)
            if self.transcoder.is_cached(song.path):
                source_path = self.transcoder.cache_path(song.path)

        self._decode_and_stream(source_path)

    def _decode_and_stream(self, source_path: str):
        cmd = [
            "ffmpeg", "-nostdin",
            "-i", source_path,
            "-vn",
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ar", config.SAMPLE_RATE,
            "-ac", config.CHANNELS,
            "-",
        ]
        try:
            with open(config.LOG_FILE, "a") as logf:
                self._decode_proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=logf,
                )
            proc = self._decode_proc
            while not self._stop_flag.is_set() and not self._skip_flag.is_set():
                chunk = proc.stdout.read(_CHUNK_SIZE)
                if not chunk:
                    break  # end of track
                if not self._write_out(chunk):
                    if not self._ensure_output_proc():
                        self.log("[player] lost Icecast connection, dropping rest of track")
                        break
                    if not self._write_out(chunk):
                        self.log("[player] Icecast write still failing after reconnect, dropping rest of track")
                        break
        except FileNotFoundError:
            self.log("[player] ERROR: ffmpeg not found on PATH")
            time.sleep(2)
        except Exception as e:
            self.log(f"[player] ERROR live-transcoding {source_path}: {e}")
        finally:
            if self._decode_proc and self._decode_proc.poll() is None:
                try:
                    self._decode_proc.terminate()
                    self._decode_proc.wait(timeout=3)
                except Exception:
                    try:
                        self._decode_proc.kill()
                    except Exception:
                        pass
            self._decode_proc = None