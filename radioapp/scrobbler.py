"""
Last.fm scrobbling, fired in a background thread so it never stalls playback.
"""
import os
import threading
import time
from typing import Optional

from radioapp import config

try:
    import pylast
    _HAVE_PYLAST = True
except ImportError:
    _HAVE_PYLAST = False


class Scrobbler:
    def __init__(self, log_fn=print):
        self.log = log_fn
        self.network = None
        self.enabled = False

        if not _HAVE_PYLAST:
            self.log("[scrobbler] pylast not installed — scrobbling disabled")
            return

        if not config.LASTFM_API_KEY or not config.LASTFM_API_SECRET:
            self.log("[scrobbler] no Last.fm API key configured (run 'setup' to add one) — scrobbling disabled")
            return

        if not os.path.isfile(config.LASTFM_SESSION_FILE):
            self.log(f"[scrobbler] session file missing ({config.LASTFM_SESSION_FILE}) — scrobbling disabled")
            return

        try:
            with open(config.LASTFM_SESSION_FILE) as f:
                session_key = f.read().strip()
            if not session_key:
                raise ValueError("session file is empty")

            self.network = pylast.LastFMNetwork(
                api_key=config.LASTFM_API_KEY,
                api_secret=config.LASTFM_API_SECRET,
            )
            self.network.session_key = session_key
            self.enabled = True
        except Exception as e:
            self.log(f"[scrobbler] init failed: {e} — scrobbling disabled")
            self.enabled = False

    def scrobble_async(self, artist: str, title: str, album: Optional[str] = None):
        if not self.enabled:
            return
        t = threading.Thread(
            target=self._scrobble, args=(artist, title, album), daemon=True
        )
        t.start()

    def now_playing_async(self, artist: str, title: str, album: Optional[str] = None):
        if not self.enabled:
            return
        t = threading.Thread(
            target=self._update_now_playing, args=(artist, title, album), daemon=True
        )
        t.start()

    def _scrobble(self, artist: str, title: str, album: Optional[str]):
        try:
            self.network.scrobble(
                artist=artist, title=title, album=album or None,
                timestamp=int(time.time()),
            )
            self.log(f"[scrobbler] scrobbled: {artist} - {title}")
        except Exception as e:
            self.log(f"[scrobbler] FAILED for '{artist} - {title}': {e}")

    def _update_now_playing(self, artist: str, title: str, album: Optional[str]):
        try:
            self.network.update_now_playing(artist=artist, title=title, album=album or None)
        except Exception as e:
            self.log(f"[scrobbler] now-playing update failed: {e}")

    @classmethod
    def login_flow(cls, print_fn=print) -> bool:
        """
        Interactive Last.fm web-auth flow: generates an auth URL, waits for
        the user to approve it in a browser, then exchanges it for a
        permanent session key and writes it to config.LASTFM_SESSION_FILE.
        Returns True on success. Safe to call any time — overwrites any
        existing session file.
        """
        if not _HAVE_PYLAST:
            print_fn("pylast not installed. Run: pip install pylast --break-system-packages")
            return False

        if not config.LASTFM_API_KEY or not config.LASTFM_API_SECRET:
            print_fn("No Last.fm API key/secret configured yet. Run 'setup' first and add them.")
            return False

        try:
            network = pylast.LastFMNetwork(
                api_key=config.LASTFM_API_KEY,
                api_secret=config.LASTFM_API_SECRET,
            )
            skg = pylast.SessionKeyGenerator(network)
            auth_url = skg.get_web_auth_url()
        except Exception as e:
            print_fn(f"Could not start Last.fm auth: {e}")
            return False

        print_fn("\nOpen this URL and click 'Allow access':")
        print_fn(f"  {auth_url}\n")
        try:
            import webbrowser
            webbrowser.open(auth_url)
        except Exception:
            pass  # headless environment, fine — user just opens the link manually

        input("Press Enter once you've approved access in the browser... ")

        session_key = None
        attempts = 5
        for attempt in range(1, attempts + 1):
            try:
                session_key = skg.get_web_auth_session_key(auth_url)
                break
            except Exception as e:
                if attempt == attempts:
                    print_fn(f"Login failed: {e}")
                    return False
                print_fn(f"Not approved yet ({e}); retrying in 3s ({attempt}/{attempts})...")
                time.sleep(3)

        if not session_key:
            print_fn("Login failed: no session key returned.")
            return False

        try:
            os.makedirs(os.path.dirname(config.LASTFM_SESSION_FILE), exist_ok=True)
            with open(config.LASTFM_SESSION_FILE, "w") as f:
                f.write(session_key)
            os.chmod(config.LASTFM_SESSION_FILE, 0o600)
        except OSError as e:
            print_fn(f"Login succeeded but failed to save session file: {e}")
            return False

        print_fn(f"Logged in to Last.fm. Session saved to {config.LASTFM_SESSION_FILE}")
        return True
