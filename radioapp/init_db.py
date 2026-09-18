#!/usr/bin/env python3
"""
init_db.py — scan the music library and (re)build the SQLite database.

Picks up every file matching config.SUPPORTED_EXTS (flac, wav, m4a, mp3,
ogg, opus, aac, wma by default), regardless of whether transcoding is
enabled — the format policy only affects playback, not what gets indexed.

Run this once initially, and again any time you add/remove/rename files.
Safe to re-run anytime: it upserts existing entries and prunes deleted files.

Usage:
    python3 -m radioapp.init_db
    python3 -m radioapp.init_db --music-dir /some/other/path
    python3 -m radioapp.init_db --prune-only     # just remove stale DB entries, no scan
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radioapp import config
from radioapp.db import Library

try:
    import mutagen
    _HAVE_MUTAGEN = True
except ImportError:
    _HAVE_MUTAGEN = False


def _read_tags(path: str):
    """
    Read artist/title/album/duration from any supported format using
    mutagen's generic loader. Different containers expose tags under
    different key names (FLAC/OGG use Vorbis comments like 'artist';
    MP3/ID3 uses 'TPE1'/'TIT2'/'TALB'; MP4/M4A uses '\xa9ART' etc.),
    so we check a few common keys per field rather than assuming one
    tagging scheme.
    """
    audio = mutagen.File(path, easy=True)  # easy=True normalizes keys
    # across formats where possible (artist/title/album become
    # consistent lowercase keys even for MP3/MP4).
    artist = title = album = None
    duration = None

    if audio is not None:
        if audio.get("artist"):
            artist = audio["artist"][0]
        if audio.get("title"):
            title = audio["title"][0]
        if audio.get("album"):
            album = audio["album"][0]
        if getattr(audio, "info", None) is not None:
            duration = getattr(audio.info, "length", None)

    return artist, title, album, duration


def scan_library(music_dir: str, db: Library, verbose: bool = True):
    start = time.time()
    found_paths = set()
    added, updated, skipped = 0, 0, 0

    for root, _dirs, files in os.walk(music_dir):
        quality_dir = os.path.relpath(root, music_dir).split(os.sep)[0]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in config.SUPPORTED_EXTS:
                continue
            path = os.path.join(root, fname)
            found_paths.add(path)

            try:
                stat = os.stat(path)
                mtime = stat.st_mtime
            except OSError as e:
                if verbose:
                    print(f"  SKIP (stat failed): {path} ({e})")
                skipped += 1
                continue

            artist, title, album, duration = "Unknown", os.path.splitext(fname)[0], "", None
            if _HAVE_MUTAGEN:
                try:
                    r_artist, r_title, r_album, r_duration = _read_tags(path)
                    artist = r_artist or artist
                    title = r_title or title
                    album = r_album or album
                    duration = r_duration
                except Exception as e:
                    if verbose:
                        print(f"  WARN (tag read failed, using filename): {path} ({e})")

            db.upsert_song(
                path=path, artist=artist, title=title, album=album,
                quality_dir=quality_dir, mtime=mtime, duration=duration,
            )
            added += 1

    db.commit()
    removed = db.remove_missing(found_paths)
    elapsed = time.time() - start

    print(f"\nScan complete in {elapsed:.1f}s")
    print(f"  Upserted: {added}")
    print(f"  Removed (no longer on disk): {removed}")
    print(f"  Total in library: {db.count()}")


def main():
    config.ensure_dirs()
    if not config.is_configured():
        print("No configuration found yet — running first-time setup.\n")
        from radioapp.setup import run_setup_wizard
        run_setup_wizard()
    config.load_config()

    parser = argparse.ArgumentParser(description="Build/update the radio song database.")
    parser.add_argument("--music-dir", default=config.MUSIC_DIR,
                         help=f"Root music directory (default: {config.MUSIC_DIR})")
    parser.add_argument("--db-path", default=config.DB_PATH,
                         help=f"SQLite DB path (default: {config.DB_PATH})")
    parser.add_argument("--prune-only", action="store_true",
                         help="Only remove DB entries for files that no longer exist; skip scanning.")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-file warnings.")
    args = parser.parse_args()

    if not _HAVE_MUTAGEN:
        print("ERROR: mutagen not installed. Run: pip install mutagen --break-system-packages")
        sys.exit(1)

    if not os.path.isdir(args.music_dir):
        print(f"ERROR: music directory not found: {args.music_dir}")
        sys.exit(1)

    db = Library(args.db_path)

    if args.prune_only:
        found_paths = set()
        for root, _dirs, files in os.walk(args.music_dir):
            for fname in files:
                if os.path.splitext(fname)[1].lower() in config.SUPPORTED_EXTS:
                    found_paths.add(os.path.join(root, fname))
        removed = db.remove_missing(found_paths)
        print(f"Pruned {removed} stale entries. Total remaining: {db.count()}")
    else:
        print(f"Scanning {args.music_dir} ...")
        scan_library(args.music_dir, db, verbose=not args.quiet)

    db.close()


if __name__ == "__main__":
    main()
