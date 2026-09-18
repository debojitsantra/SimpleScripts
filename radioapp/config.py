
#Central configuration for the radio app.

import json
import os

CONFIG_DIR = os.path.expanduser("~/.radioapp")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

MP3_BITRATE = "320k"
SAMPLE_RATE = "44100"
CHANNELS = "2"
FLAC_EXT = ".flac"  # kept for backwards compat; scanning now uses SUPPORTED_EXTS
PRELOAD_DEPTH = 1
SUPPORTED_EXTS = {".flac", ".wav", ".m4a", ".mp3", ".ogg", ".opus", ".aac", ".wma"}
TRANSCODE_TARGET_EXTS = {".flac", ".wav"}
TRANSCODING_ENABLED = True

RUNTIME_DIR = os.path.join(CONFIG_DIR, "run")
PID_FILE = os.path.join(RUNTIME_DIR, "radio.pid")
LOG_FILE = os.path.join(RUNTIME_DIR, "radio.log")
TRANSCODE_CACHE_DIR = os.path.join(CONFIG_DIR, "cache")
DB_PATH = os.path.join(CONFIG_DIR, "library.db")
LASTFM_SESSION_FILE = os.path.join(CONFIG_DIR, "lastfm_session")

MUSIC_DIR = None
ICECAST_HOST = None
ICECAST_PORT = None
ICECAST_SOURCE_PASSWORD = None
ICECAST_MOUNT = None
ICECAST_BIN = None
ICECAST_CONFIG = None
LASTFM_API_KEY = None
LASTFM_API_SECRET = None


def needs_transcoding(path: str) -> bool:
    if not TRANSCODING_ENABLED:
        return False
    ext = os.path.splitext(path)[1].lower()
    return ext in TRANSCODE_TARGET_EXTS


def icecast_url() -> str:
    return (
        f"icecast://source:{ICECAST_SOURCE_PASSWORD}@"
        f"{ICECAST_HOST}:{ICECAST_PORT}{ICECAST_MOUNT}"
    )


def is_configured() -> bool:
    return os.path.isfile(CONFIG_FILE)


def ensure_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    os.makedirs(TRANSCODE_CACHE_DIR, exist_ok=True)


def load_config():
    """Populate this module's user-setting globals from CONFIG_FILE."""
    global MUSIC_DIR, ICECAST_HOST, ICECAST_PORT, ICECAST_SOURCE_PASSWORD
    global ICECAST_MOUNT, ICECAST_BIN, ICECAST_CONFIG
    global LASTFM_API_KEY, LASTFM_API_SECRET
    global TRANSCODING_ENABLED

    if not is_configured():
        raise RuntimeError(
            f"No configuration found at {CONFIG_FILE}. "
            f"Run the setup wizard first (it runs automatically on first "
            f"launch, or manually: python3 -m radioapp.setup)"
        )

    with open(CONFIG_FILE) as f:
        data = json.load(f)

    MUSIC_DIR = data.get("music_dir")
    ICECAST_HOST = data.get("icecast_host", "localhost")
    ICECAST_PORT = data.get("icecast_port", 8000)
    ICECAST_SOURCE_PASSWORD = data.get("icecast_source_password")
    ICECAST_MOUNT = data.get("icecast_mount", "/stream.mp3")
    ICECAST_BIN = data.get("icecast_bin") or "icecast"
    ICECAST_CONFIG = data.get("icecast_config") or None
    LASTFM_API_KEY = data.get("lastfm_api_key") or None
    LASTFM_API_SECRET = data.get("lastfm_api_secret") or None
    TRANSCODING_ENABLED = data.get("transcoding_enabled", True)


def save_config(data: dict):
    ensure_dirs()
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
    try:
        # Holds the Icecast source password + Last.fm API secret.
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass  
