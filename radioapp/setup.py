#!/usr/bin/env python3
"""
interactive first-run configuration wizard.

Collects everything the app needs — music library location, Icecast
connection details, optional Last.fm scrobbling keys — and saves it to
~/.radioapp/config.json so you never have to enter it again.

Runs automatically on first launch of the app. Re-run any time with:
    python3 -m radioapp.setup
or the in-app `setup` shell command.
"""
import getpass
import json
import os
import sys

from radioapp import config


def _ask(prompt: str, default: str = "", required: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        val = input(f"{prompt}{suffix}: ").strip()
        if not val:
            val = default
        if val or not required:
            return val
        print("  This value is required.")


def _ask_secret(prompt: str, has_existing: bool = False, required: bool = False) -> str:
    note = " (leave blank to keep current)" if has_existing else ""
    while True:
        val = getpass.getpass(f"{prompt}{note}: ").strip()
        if val or has_existing or not required:
            return val
        print("  This value is required.")


def _load_existing() -> dict:
    if not os.path.isfile(config.CONFIG_FILE):
        return {}
    try:
        with open(config.CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def run_setup_wizard(reconfigure: bool = False):
    print("=" * 60)
    print("Radio app setup" + (" (reconfigure)" if reconfigure else ""))
    print("=" * 60)
    print("This only needs to run once — everything is saved to:")
    print(f"  {config.CONFIG_FILE}")
    print("Press Enter to accept a default shown in [brackets].\n")

    existing = _load_existing()

    print("-- Music library --")
    while True:
        music_dir = _ask(
            "Folder containing your music (scanned recursively for .flac files)",
            default=existing.get("music_dir", ""),
            required=True,
        )
        music_dir = os.path.abspath(os.path.expanduser(music_dir))
        if os.path.isdir(music_dir):
            break
        print(f"  '{music_dir}' doesn't exist or isn't a folder — try again.")

    print("\n-- Icecast (your streaming server) --")
    icecast_host = _ask("Icecast host", default=existing.get("icecast_host", "localhost"))

    port_default = str(existing.get("icecast_port", 8000))
    while True:
        icecast_port_raw = _ask("Icecast port", default=port_default)
        try:
            icecast_port = int(icecast_port_raw)
            break
        except ValueError:
            print("  Port must be a number.")

    icecast_mount = _ask("Icecast mount point", default=existing.get("icecast_mount", "/stream.mp3"))
    if not icecast_mount.startswith("/"):
        icecast_mount = "/" + icecast_mount

    icecast_source_password = _ask_secret(
        "Icecast SOURCE password",
        has_existing=bool(existing.get("icecast_source_password")),
        required=True,
    ) or existing.get("icecast_source_password", "")

    icecast_bin = _ask("Icecast executable name or full path", default=existing.get("icecast_bin", "icecast"))
    icecast_config = _ask(
        "Path to icecast.xml (leave blank if Icecast is already running, "
        "or you'll start it yourself)",
        default=existing.get("icecast_config") or "",
    )

    print("\n-- Transcoding --")
    print("If off, every file streams as-is (no re-encoding at all) — fastest,")
    print("but listeners get whatever bitrate/format your files already are,")
    print(f"and non-MP3 formats like FLAC/WAV may not play in every client.")
    print(f"If on, only hi-res formats ({', '.join(sorted(config.TRANSCODE_TARGET_EXTS))}) get")
    print("transcoded to 320kbps MP3; already-compressed formats (mp3, m4a, ogg...)")
    print("still stream untouched either way.")
    existing_transcoding = existing.get("transcoding_enabled", True)
    transcoding_raw = _ask(
        "Enable transcoding? (y/n)",
        default="y" if existing_transcoding else "n",
    ).strip().lower()
    transcoding_enabled = transcoding_raw in ("y", "yes", "true", "1")

    print("\n-- Last.fm scrobbling (optional — leave blank to skip) --")
    lastfm_api_key = _ask("Last.fm API key", default=existing.get("lastfm_api_key") or "")
    lastfm_api_secret = existing.get("lastfm_api_secret", "")
    if lastfm_api_key:
        lastfm_api_secret = _ask_secret(
            "Last.fm API secret",
            has_existing=bool(existing.get("lastfm_api_secret")),
        ) or lastfm_api_secret

    data = {
        "music_dir": music_dir,
        "icecast_host": icecast_host,
        "icecast_port": icecast_port,
        "icecast_mount": icecast_mount,
        "icecast_source_password": icecast_source_password,
        "icecast_bin": icecast_bin,
        "icecast_config": icecast_config or None,
        "transcoding_enabled": transcoding_enabled,
        "lastfm_api_key": lastfm_api_key or None,
        "lastfm_api_secret": lastfm_api_secret or None,
    }

    config.save_config(data)
    print(f"\nSaved to {config.CONFIG_FILE}.")
    print("Run 'python3 -m radioapp.setup' any time to change these settings,")
    print("or use the in-app 'setup' command (restart required after).\n")


def main():
    config.ensure_dirs()
    run_setup_wizard(reconfigure=config.is_configured())


if __name__ == "__main__":
    sys.exit(main())
