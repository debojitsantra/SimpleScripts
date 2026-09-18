#Pre-transcode engine.

import hashlib
import os
import subprocess
import threading
from typing import Optional

from radioapp import config


def _cache_path_for(source_path: str) -> str:
    h = hashlib.sha1(source_path.encode("utf-8")).hexdigest()
    return os.path.join(config.TRANSCODE_CACHE_DIR, f"{h}.mp3")


class Transcoder:
    """
    Manages a single in-flight background transcode job at a time
    (matches PRELOAD_DEPTH=1 use case: "convert the next song while
    this one plays"). Thread-safe enough for our single-producer,
    single-consumer usage pattern.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._job_thread: Optional[threading.Thread] = None
        self._job_source: Optional[str] = None
        self._job_done = threading.Event()
        self._job_ok = False

    def cache_path(self, source_path: str) -> str:
        return _cache_path_for(source_path)

    def is_cached(self, source_path: str) -> bool:
        path = self.cache_path(source_path)
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def start_preload(self, source_path: str):
        #Kick off a background transcode for source_path, if not already cached/in-flight.
        if self.is_cached(source_path):
            return
        with self._lock:
            if self._job_thread and self._job_thread.is_alive() and self._job_source == source_path:
                return  
            self._job_source = source_path
            self._job_done.clear()
            self._job_ok = False
            self._job_thread = threading.Thread(
                target=self._run_transcode, args=(source_path,), daemon=True
            )
            self._job_thread.start()

    def _run_transcode(self, source_path: str):
        out_path = self.cache_path(source_path)
        tmp_path = out_path + ".part"
        try:
            cmd = [
                "ffmpeg", "-nostdin", "-y",
                "-i", source_path,
                "-vn",  # drop embedded cover art / video streams
                "-ar", config.SAMPLE_RATE,
                "-ac", config.CHANNELS,
                "-b:a", config.MP3_BITRATE,
                "-f", "mp3",
                tmp_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0 and os.path.isfile(tmp_path) and os.path.getsize(tmp_path) > 0:
                os.replace(tmp_path, out_path)
                self._job_ok = True
            else:
                self._job_ok = False
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        except Exception:
            self._job_ok = False
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        finally:
            self._job_done.set()

    def wait_for(self, source_path: str, timeout: Optional[float] = None) -> bool:
        #Block until the preload job for source_path finishes (or timeout). Returns success bool.
        with self._lock:
            same_job = self._job_source == source_path and self._job_thread is not None
        if same_job:
            self._job_done.wait(timeout=timeout)
            return self._job_ok
        return self.is_cached(source_path)

    def cleanup_cache(self, keep_paths: Optional[set] = None, max_files: int = 5):
        keep_paths = keep_paths or set()
        keep_cache_names = {os.path.basename(_cache_path_for(p)) for p in keep_paths}
        try:
            entries = []
            for fname in os.listdir(config.TRANSCODE_CACHE_DIR):
                if not fname.endswith(".mp3"):
                    continue
                fpath = os.path.join(config.TRANSCODE_CACHE_DIR, fname)
                entries.append((fpath, os.path.getmtime(fpath), fname))
            entries.sort(key=lambda x: x[1], reverse=True)

            for i, (fpath, _mtime, fname) in enumerate(entries):
                if fname in keep_cache_names:
                    continue
                if i >= max_files:
                    try:
                        os.remove(fpath)
                    except OSError:
                        pass
        except FileNotFoundError:
            pass
