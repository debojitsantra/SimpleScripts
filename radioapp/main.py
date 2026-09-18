#!/usr/bin/env python3
import atexit
import os
import shutil
import signal
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radioapp import config
from radioapp.db import Library
from radioapp.player import Player
from radioapp.setup import run_setup_wizard
from radioapp.shell import Shell


class App:
    def __init__(self):
        config.ensure_dirs()
        if not config.is_configured():
            run_setup_wizard()
        config.load_config()

        self._check_single_instance()

        self.db = Library(config.DB_PATH)
        if self.db.count() == 0:
            print(
                f"WARNING: library database is empty ({config.DB_PATH}).\n"
                f"Run: python3 -m radioapp.init_db\n"
            )

        self.player = Player(self.db, log_fn=self._log)
        self.shell = Shell(self.player, self.db, log_fn=self._log)

        self._icecast_proc = None
        self._we_started_icecast = False

    #log everything 

    def _log(self, msg: str):
        line = f"{msg}"
        print(line)
        try:
            with open(config.LOG_FILE, "a") as f:
                f.write(line + "\n")
        except Exception:
            pass

    #instance guard

    def _check_single_instance(self):
        pidfile = config.PID_FILE
        if os.path.isfile(pidfile):
            try:
                with open(pidfile) as f:
                    old_pid = int(f.read().strip())
                os.kill(old_pid, 0)  # raises OSError if not running
                print(f"Radio already running (PID {old_pid}). Exiting.")
                sys.exit(1)
            except (OSError, ValueError):
                pass  # stale pidfile, fine to proceed
        with open(pidfile, "w") as f:
            f.write(str(os.getpid()))

    #manage icecast

    def _is_icecast_running(self) -> bool:
        try:
            with socket.create_connection((config.ICECAST_HOST, config.ICECAST_PORT), timeout=1):
                return True
        except OSError:
            return False

    def _start_icecast(self):
        if self._is_icecast_running():
            self._log(f"[main] Something is already listening on "
                       f"{config.ICECAST_HOST}:{config.ICECAST_PORT} — assuming it's Icecast.")
            return

        if not config.ICECAST_CONFIG:
            self._log(
                "[main] No Icecast config path set, and nothing is listening on "
                f"{config.ICECAST_HOST}:{config.ICECAST_PORT}. Start Icecast yourself, "
                "or set a config path via the 'setup' command."
            )
            return

        if not shutil.which(config.ICECAST_BIN):
            self._log(f"[main] '{config.ICECAST_BIN}' not found on PATH — "
                       f"install Icecast or start it manually.")
            return

        self._log("[main] Starting Icecast...")
        try:
            with open(config.LOG_FILE, "a") as logf:
                self._icecast_proc = subprocess.Popen(
                    [config.ICECAST_BIN, "-c", config.ICECAST_CONFIG],
                    stdout=logf, stderr=logf,
                )
            self._we_started_icecast = True
            time.sleep(2)
        except FileNotFoundError:
            self._log("[main] ERROR: icecast binary not found")

    #lifecycle

    def cleanup(self, *_args):
        self._log("\n[main] Shutting down...")

        self.player.stop()

        if self._icecast_proc and self._icecast_proc.poll() is None:
            try:
                self._icecast_proc.terminate()
                self._icecast_proc.wait(timeout=3)
            except Exception:
                try:
                    self._icecast_proc.kill()
                except Exception:
                    pass
        elif self._we_started_icecast and shutil.which("pkill"):
            subprocess.run(["pkill", "-x", os.path.basename(config.ICECAST_BIN)], capture_output=True)

        if shutil.which("pkill"):
            for pattern in (config.ICECAST_MOUNT, config.MUSIC_DIR, config.TRANSCODE_CACHE_DIR):
                if pattern:
                    subprocess.run(["pkill", "-f", f"ffmpeg.*{pattern}"], capture_output=True)

        if shutil.which("termux-wake-unlock"):
            subprocess.run(["termux-wake-unlock"], capture_output=True)

        try:
            if os.path.isfile(config.PID_FILE):
                os.remove(config.PID_FILE)
        except OSError:
            pass

        self.db.close()
        self._log("[main] Stopped cleanly.")

    def run(self):
        def handle_signal(signum, frame):
            self.cleanup()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_signal)
        try:
            signal.signal(signal.SIGTERM, handle_signal)
        except (AttributeError, ValueError):
            pass 
        atexit.register(lambda: None)  

        try:
            self._start_icecast()

            if shutil.which("termux-wake-lock"):
                subprocess.run(["termux-wake-lock"], capture_output=True)

            self.player.start()
            self._log("[main] Playback started.")

            self.shell.run()
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()


def main():
    app = App()
    app.run()


if __name__ == "__main__":
    main()
