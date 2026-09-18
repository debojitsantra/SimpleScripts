"""
Interactive command shell for the radio app.

Commands:
    shuffle                 - switch to shuffle mode (random order, reshuffles each lap)
    sort shuffle             - alias for shuffle
    sort newest               - play newest-added songs first
    sort oldest                - play oldest-added songs first
    search <query>            - fuzzy search and pick a song to play now;
                                 afterwards playback resumes the mode you were in
    login lastfm              - authorize scrobbling with your Last.fm account
    setup                    - re-run the configuration wizard (restart to apply)
    transcoding [on|off]        - show or change transcoding; off streams every
                                 file exactly as stored, no re-encoding at all
    skip / next                - skip current song
    status / now               - show what's playing and current mode
    rescan                    - re-run the library scan (add new files, prune deleted)
    help                     - show this list
    quit / exit / q            - stop everything and exit
"""
import sys
import threading

from radioapp import config
from radioapp.db import Library, Song
from radioapp.player import Player, Mode
from radioapp.scrobbler import Scrobbler


HELP_TEXT = """
Available commands:
  shuffle                 Random playback (reshuffles each lap through the library)
  sort shuffle              Same as: shuffle
  sort newest                Play newest-added songs first, in order
  sort oldest                 Play oldest-added songs first, in order
  search <query>             Fuzzy-search your library and play a match now;
                             resumes your previous mode after that one song
  login lastfm               Authorize scrobbling with your Last.fm account
  setup                     Re-run the configuration wizard (restart to apply)
  transcoding [on|off]         Show or change transcoding (off = stream files as-is)
  skip | next                 Skip to the next song
  status | now                Show current song and mode
  rescan                    Re-scan music folder into the database
  help                     Show this help
  quit | exit | q              Stop the radio and exit
"""


class Shell:
    def __init__(self, player: Player, db: Library, log_fn=print):
        self.player = player
        self.db = db
        self.log = log_fn
        self._stop = threading.Event()

    def _print(self, msg: str):
        print(msg)

    def _handle_search(self, query: str):
        if not query:
            self._print("Usage: search <text>")
            return
        results = self.db.search(query, limit=8)
        if not results:
            self._print(f"No matches for '{query}'")
            return

        self._print(f"\nMatches for '{query}':")
        for i, song in enumerate(results, 1):
            tag = song.quality_dir or song.ext.lstrip(".").upper()
            self._print(f"  {i}. {song.display()}  [{tag}]")

        choice = input("Play which number? (Enter to cancel): ").strip()
        if not choice:
            self._print("Cancelled.")
            return
        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(results)):
                raise ValueError()
        except ValueError:
            self._print("Invalid selection.")
            return

        song = results[idx]
        self._print(f"Playing now: {song.display()}")
        self.player.play_now(song)

    def _handle_rescan(self):
        from radioapp import config
        from radioapp.init_db import scan_library
        self._print("Rescanning library...")
        scan_library(config.MUSIC_DIR, self.db, verbose=False)
        self._print(f"Rescan complete. {self.db.count()} songs in library.")

    def _handle_login_lastfm(self):
        self._print("Starting Last.fm login...")
        ok = Scrobbler.login_flow(print_fn=self._print)
        if not ok:
            self._print("Last.fm login failed. Scrobbling remains disabled.")
            return
        self.player.scrobbler = Scrobbler(log_fn=self.log)
        if self.player.scrobbler.enabled:
            self._print("Scrobbling is now enabled.")
        else:
            self._print("Session saved, but the scrobbler didn't come up — check the log.")

    def _handle_setup(self):
        from radioapp.setup import run_setup_wizard
        run_setup_wizard(reconfigure=True)
        self._print("Settings saved. Restart the app for changes to fully take effect.")

    def dispatch(self, line: str) -> bool:
        """Returns False if the shell should exit."""
        line = line.strip()
        if not line:
            return True

        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("quit", "exit", "q"):
            return False

        elif cmd == "help":
            self._print(HELP_TEXT)

        elif cmd == "shuffle":
            self.player.set_mode(Mode.SHUFFLE)
            self._print("Mode: shuffle")

        elif cmd == "sort":
            sub = arg.lower().strip()
            if sub == "shuffle":
                self.player.set_mode(Mode.SHUFFLE)
                self._print("Mode: shuffle")
            elif sub == "newest":
                self.player.set_mode(Mode.SORT_NEWEST)
                self._print("Mode: sort newest")
            elif sub == "oldest":
                self.player.set_mode(Mode.SORT_OLDEST)
                self._print("Mode: sort oldest")
            else:
                self._print("Usage: sort <shuffle|newest|oldest>")

        elif cmd == "search":
            self._handle_search(arg)

        elif cmd == "login":
            sub = arg.lower().strip()
            if sub == "lastfm":
                self._handle_login_lastfm()
            else:
                self._print("Usage: login lastfm")

        elif cmd == "setup":
            self._handle_setup()

        elif cmd == "transcoding":
            sub = arg.lower().strip()
            if sub == "":
                state = "on" if config.TRANSCODING_ENABLED else "off"
                targets = ", ".join(sorted(config.TRANSCODE_TARGET_EXTS))
                self._print(f"Transcoding is {state}. Target formats: {targets}")
            elif sub in ("on", "off"):
                config.TRANSCODING_ENABLED = (sub == "on")
                self._print(f"Transcoding is now {sub}. "
                            f"(This is for the current session only — "
                            f"run 'setup' to save it permanently.)")
            else:
                self._print("Usage: transcoding [on|off]")

        elif cmd in ("skip", "next"):
            self.player.skip()
            self._print("Skipped.")

        elif cmd in ("status", "now"):
            st = self.player.status()
            self._print(
                f"Mode: {st['mode']} | Track {st['queue_pos'] + 1}/{st['queue_len']} | "
                f"Now playing: {st['current'] or '(starting...)'}"
            )

        elif cmd == "rescan":
            self._handle_rescan()

        else:
            self._print(f"Unknown command: {cmd!r}. Type 'help' for options.")

        return True

    def run(self):
        self._print("Radio command shell. Type 'help' for commands, Ctrl+C to stop.")
        while True:
            try:
                line = input("radio> ")
            except EOFError:
                break
            except KeyboardInterrupt:
                raise
            if not self.dispatch(line):
                break
