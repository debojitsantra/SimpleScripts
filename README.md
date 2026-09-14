# SimpleScripts

simple scripts i use everyday for diff tasks

## Scripts

### `down.py`

```
makes download process easy as i am finding yt videos to download
```

### `ytd.py`

```
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
```
