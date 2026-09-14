#!/usr/bin/env python3
"""
Walks a NewPipe subscriptions export, and for each
channel checks whether its newest public video is one we haven't already
downloaded (tracked in a history file, one entry per channel). If it's new:
likes it (direct HTTP request using your YouTube cookies — no browser
needed), downloads it as audio or video via yt-dlp, then replaces that channel's
history entry with the new video (old entry is dropped).

Usage:
    # First time setup: record current latest videos as baseline, without
    # downloading anything (so you don't get flooded with your whole backlog)
    python3 ytd.py subscriptions.json --cookies cookies.txt --init-history

    # Normal run: only new videos since the baseline get liked + downloaded
    python3 ytd.py subscriptions.json --cookies cookies.txt --out ./downloads

Requirements:
    pip install yt-dlp requests

cookies.txt must be a Netscape-format cookie file exported from a browser
where you're logged into YouTube (use "Get cookies.txt LOCALLY"
extension..i use it). This is the same file format yt-dlp's --cookies flag expects.
"""

import argparse
import http.cookiejar
import json
import re
import sys
import time
from pathlib import Path

import requests
import yt_dlp

YOUTUBE_LIKE_ENDPOINT = "https://www.youtube.com/youtubei/v1/like/like"
YOUTUBE_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"

INNERTUBE_CONTEXT = {
    "client": {
        "clientName": "WEB",
        "clientVersion": "2.20240101.00.00",
    }
}
INNERTUBE_API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"

VIDEO_ENABLED = False #If it False then VIDEO_QUALITY & DOWNLOAD_AUDIO_WITH_VIDEO is completely ignored and downloads audio only 
VIDEO_QUALITY = "1080"
DOWNLOAD_AUDIO_WITH_VIDEO = True


def log(msg):
    print(f"[yt-dlp] {msg}", flush=True)


def load_channels(export_path):
    data = json.loads(Path(export_path).read_text(encoding="utf-8"))
    channels = []
    for sub in data.get("subscriptions", []):
        url = sub.get("url", "")
        name = sub.get("name", "unknown")
        m = re.search(r"/channel/([A-Za-z0-9_-]+)", url)
        if not m:
            log(f"  skip (no channel id found): {name} -> {url}")
            continue
        channels.append({"name": name, "channel_id": m.group(1), "url": url})
    return channels


def get_latest_public_video(channel_url, cookiefile=None):
    videos_url = channel_url.rstrip("/") + "/videos"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlist_items": "1",
        "skip_download": True,
    }
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(videos_url, download=False)
    except Exception as e:
        log(f"  ERROR fetching channel videos: {e}")
        return None

    entries = info.get("entries") if info else None
    if not entries:
        return None

    entry = entries[0]
    video_id = entry.get("id")
    title = entry.get("title", "")
    if not video_id:
        return None
    return video_id, title, YOUTUBE_WATCH_URL.format(video_id=video_id)


def build_session(cookiefile):
    jar = http.cookiejar.MozillaCookieJar(cookiefile)
    jar.load(ignore_discard=True, ignore_expires=True)
    session = requests.Session()
    session.cookies = jar
    return session


def get_sapisid_hash(session, origin="https://www.youtube.com"):
    import hashlib

    sapisid = None
    for cookie in session.cookies:
        if cookie.name in ("SAPISID", "__Secure-3PAPISID"):
            sapisid = cookie.value
            break
    if not sapisid:
        raise RuntimeError(
            "No SAPISID cookie found in cookies.txt — make sure you exported "
            "cookies while logged into YouTube."
        )

    timestamp = str(int(time.time()))
    to_hash = f"{timestamp} {sapisid} {origin}"
    digest = hashlib.sha1(to_hash.encode("utf-8")).hexdigest()
    return f"{timestamp}_{digest}"


def like_video(session, video_id):
    sapisidhash = get_sapisid_hash(session)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SAPISIDHASH {sapisidhash}",
        "X-Origin": "https://www.youtube.com",
        "X-Goog-AuthUser": "0",
        "Origin": "https://www.youtube.com",
        "Referer": f"https://www.youtube.com/watch?v={video_id}",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    payload = {
        "context": INNERTUBE_CONTEXT,
        "target": {"videoId": video_id},
    }

    resp = session.post(
        f"{YOUTUBE_LIKE_ENDPOINT}?key={INNERTUBE_API_KEY}",
        headers=headers,
        json=payload,
        timeout=15,
    )

    if resp.status_code == 200:
        return True
    log(f"  like request failed: HTTP {resp.status_code} — {resp.text[:200]}")
    return False


def download_audio(video_url, out_dir, cookiefile=None):
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    if not VIDEO_ENABLED:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(Path(out_dir) / "%(uploader)s/%(title)s [%(id)s].%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
            }],
            "quiet": False,
            "no_warnings": True,
            "ignoreerrors": True,
        }
        if cookiefile:
            ydl_opts["cookiefile"] = cookiefile

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return

    if DOWNLOAD_AUDIO_WITH_VIDEO:
        fmt = f"bestvideo[height<={VIDEO_QUALITY}]+bestaudio/best[height<={VIDEO_QUALITY}]"
    else:
        fmt = f"bestvideo[height<={VIDEO_QUALITY}]/best[height<={VIDEO_QUALITY}]"

    ydl_opts = {
        "format": fmt,
        "outtmpl": str(Path(out_dir) / "%(uploader)s/%(title)s [%(id)s].%(ext)s"),
        "quiet": False,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])


def load_history(history_path):
    if Path(history_path).exists():
        return json.loads(Path(history_path).read_text())
    return {}


def save_history(history_path, history):
    Path(history_path).write_text(json.dumps(history, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", help="Path to Pipepipe/NewPipe subscriptions JSON export")
    parser.add_argument("--cookies", required=True, help="Path to cookies.txt (Netscape format)")
    parser.add_argument("--out", default="./downloads", help="Output directory for audio files")
    parser.add_argument(
        "--history", default="./ytdlp_history.json",
        help="Path to a JSON file recording the last downloaded video ID per "
             "channel. A channel is only re-downloaded once its newest "
             "public video differs from what's stored here."
    )
    parser.add_argument("--no-like", action="store_true", help="Skip liking, only download audio")
    parser.add_argument(
        "--init-history", action="store_true",
        help="Don't like or download anything — just record each channel's "
             "current newest video into the history file, so future runs "
             "treat it as the baseline and only fetch videos published "
             "after this point. Use this on first setup so the script "
             "doesn't try to download your entire backlog."
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print what would happen, no writes")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds to wait between channels")
    args = parser.parse_args()

    channels = load_channels(args.export)
    log(f"Loaded {len(channels)} channels from export.")

    history = load_history(args.history)

    session = None
    if not args.no_like and not args.init_history:
        try:
            session = build_session(args.cookies)
        except Exception as e:
            log(f"Could not load cookies for liking: {e}")
            log("Continuing without liking (use --no-like to silence this).")

    for ch in channels:
        log(f"Channel: {ch['name']} ({ch['channel_id']})")

        result = get_latest_public_video(ch["url"], cookiefile=args.cookies)
        if not result:
            log("  no public video found, skipping")
            continue

        video_id, title, watch_url = result
        last_seen = history.get(ch["channel_id"], {}).get("video_id")

        if last_seen == video_id:
            log(f"  no new video (latest is still {video_id}), skipping")
            continue

        log(f"  new video: {title} ({watch_url})")
        if last_seen:
            log(f"  (previously downloaded: {last_seen})")

        if args.init_history:
            log("  [init-history] recording as baseline, not downloading")
            if not args.dry_run:
                history[ch["channel_id"]] = {
                    "video_id": video_id, "title": title, "name": ch["name"]
                }
                save_history(args.history, history)
            continue

        if args.dry_run:
            log("  [dry-run] would like + download + update history")
            continue

        liked = False
        if session:
            try:
                liked = like_video(session, video_id)
                log(f"  like: {'ok' if liked else 'failed'}")
            except Exception as e:
                log(f"  like error: {e}")

        try:
            download_audio(watch_url, args.out, cookiefile=args.cookies)
            log("  audio downloaded")
        except Exception as e:
            log(f"  download error: {e} — history NOT updated, will retry next run")
            time.sleep(args.delay)
            continue


        history[ch["channel_id"]] = {
            "video_id": video_id, "title": title, "name": ch["name"], "liked": liked
        }
        save_history(args.history, history)
        time.sleep(args.delay)

    log("Done.")


if __name__ == "__main__":
    main()