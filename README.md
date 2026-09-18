# SimpleScripts

simple scripts i use everyday for diff tasks

## Scripts

### `down.py`

  makes download process easy as i am finding yt videos to download

### `ytd.py`

Walks a NewPipe subscriptions export, and for each
channel checks whether its newest public video is one we haven't already
downloaded (tracked in a history file, one entry per channel). If it's new:
likes it (direct HTTP request using your YouTube cookies — no browser
needed), downloads it as audio or video via yt-dlp, then replaces that channel's
history entry with the new video (old entry is dropped).

### `radioapp`

 Personal radio streamer. Streams your library to Icecast as
Source or 320kbps MP3, and can
scrobble to Last.fm. Runs anywhere Python, ffmpeg, and Icecast are
installed : Linux, macOS, Windows, or Termux/Android.
