"""
SQLite-backed song library with fuzzy search.

Schema:
    songs(
        id INTEGER PRIMARY KEY,
        path TEXT UNIQUE NOT NULL,
        artist TEXT,
        title TEXT,
        album TEXT,
        quality_dir TEXT,      -- e.g. "24bit_192kHz"
        mtime REAL NOT NULL,   -- file modified time, used for newest/oldest sort
        duration REAL,
        added_at REAL NOT NULL
    )

Fuzzy search tries rapidfuzz first (fast, good ranking); falls back to
stdlib difflib if rapidfuzz isn't installed, so the app still runs with
zero extra dependencies.
"""
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

try:
    from rapidfuzz import fuzz as _rf_fuzz
    _HAVE_RAPIDFUZZ = True
except ImportError:
    import difflib
    _HAVE_RAPIDFUZZ = False


@dataclass
class Song:
    id: int
    path: str
    artist: str
    title: str
    album: str
    quality_dir: str
    mtime: float
    duration: Optional[float]

    def display(self) -> str:
        if self.artist and self.artist != "Unknown":
            return f"{self.artist} - {self.title}"
        return self.title or os.path.basename(self.path)


SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    artist TEXT,
    title TEXT,
    album TEXT,
    quality_dir TEXT,
    mtime REAL NOT NULL,
    duration REAL,
    added_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_songs_mtime ON songs(mtime);
CREATE INDEX IF NOT EXISTS idx_songs_artist ON songs(artist);
CREATE INDEX IF NOT EXISTS idx_songs_title ON songs(title);
"""


class Library:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def close(self):
        with self._lock:
            self.conn.close()


    def upsert_song(self, path: str, artist: str, title: str, album: str,
                     quality_dir: str, mtime: float, duration: Optional[float]):
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO songs (path, artist, title, album, quality_dir, mtime, duration, added_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    artist=excluded.artist,
                    title=excluded.title,
                    album=excluded.album,
                    quality_dir=excluded.quality_dir,
                    mtime=excluded.mtime,
                    duration=excluded.duration
                """,
                (path, artist, title, album, quality_dir, mtime, duration, time.time()),
            )

    def commit(self):
        with self._lock:
            self.conn.commit()

    def remove_missing(self, existing_paths: set):
        """Delete DB rows whose file no longer exists on disk."""
        with self._lock:
            rows = self.conn.execute("SELECT path FROM songs").fetchall()
            stale = [r["path"] for r in rows if r["path"] not in existing_paths]
            if stale:
                self.conn.executemany("DELETE FROM songs WHERE path = ?", [(p,) for p in stale])
                self.conn.commit()
            return len(stale)


    def count(self) -> int:
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) c FROM songs").fetchone()["c"]

    def _row_to_song(self, row) -> Song:
        return Song(
            id=row["id"], path=row["path"], artist=row["artist"] or "Unknown",
            title=row["title"] or os.path.basename(row["path"]),
            album=row["album"] or "", quality_dir=row["quality_dir"] or "",
            mtime=row["mtime"], duration=row["duration"],
        )

    def all_songs(self) -> List[Song]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM songs").fetchall()
        return [self._row_to_song(r) for r in rows]

    def songs_sorted_by_mtime(self, newest_first: bool = True) -> List[Song]:
        order = "DESC" if newest_first else "ASC"
        with self._lock:
            rows = self.conn.execute(f"SELECT * FROM songs ORDER BY mtime {order}").fetchall()
        return [self._row_to_song(r) for r in rows]

    def get_by_path(self, path: str) -> Optional[Song]:
        with self._lock:
            row = self.conn.execute("SELECT * FROM songs WHERE path = ?", (path,)).fetchone()
        return self._row_to_song(row) if row else None

    def search(self, query: str, limit: int = 15) -> List[Song]:
        """Fuzzy search across artist + title + album + filename."""
        query = query.strip()
        if not query:
            return []

        with self._lock:
            rows = self.conn.execute("SELECT * FROM songs").fetchall()
        candidates = []
        for r in rows:
            song = self._row_to_song(r)
            haystack = f"{song.artist} {song.title} {song.album} {os.path.basename(song.path)}"
            candidates.append((song, haystack))

        if _HAVE_RAPIDFUZZ:
            scored = [
                (song, _rf_fuzz.WRatio(query, haystack))
                for song, haystack in candidates
            ]
        else:
            scored = [
                (song, difflib.SequenceMatcher(None, query.lower(), haystack.lower()).ratio() * 100)
                for song, haystack in candidates
            ]

        scored.sort(key=lambda x: x[1], reverse=True)
        # Filter out near-zero matches, keep top N
        results = [song for song, score in scored if score > 30][:limit]
        return results
