# radioapp

Personal radio streamer. Streams your library to Icecast as
Source or 320kbps MP3, and can
scrobble to Last.fm. Runs anywhere Python, ffmpeg, and Icecast are
installed : Linux, macOS, Windows, or Termux/Android.

## Install

```bash
pip install pylast mutagen --break-system-packages
pip install rapidfuzz --break-system-packages   # optional, better search
```

You'll also need `ffmpeg` on your PATH, and an Icecast server (either
running already, or let the app start it for you — see setup below).

## Setup

Nothing to hand-edit. On first run, the app walks you through a setup
wizard and saves everything to `~/.radioapp/config.json` — you won't
be asked again:

```bash
python3 -m radioapp.main
```

It'll ask for:

- **Music folder** — scanned recursively for `.flac` files
- **Icecast host / port / mount / source password**
- **Icecast binary + config path** — optional; leave blank if Icecast
  is already running (as a service, started separately, etc.) and the
  app will just connect to it instead of starting its own
- **Last.fm API key + secret** — optional, skip to leave scrobbling off

Re-run the wizard any time with:

```bash
python3 -m radioapp.setup
```

or the in-app `setup` command (restart to apply changes).

Build the song database (re-run anytime you add/remove music):

```bash
python3 -m radioapp.init_db
```

### Last.fm scrobbling

If you gave it a Last.fm API key/secret during setup, authorize your
account from inside the app:

```
radio> login lastfm
```

This opens a Last.fm approval link, waits for you to confirm in a
browser, then saves a session — scrobbling turns on immediately, no
restart needed.

## Run

```bash
python3 -m radioapp.main
```

Drops you into a command shell. `Ctrl+C` stops everything cleanly.

## Commands

```
shuffle              random playback
sort shuffle          same as shuffle
sort newest            newest songs first
sort oldest             oldest songs first
search <text>          fuzzy search, play a match, then resume previous mode
login lastfm           authorize Last.fm scrobbling
setup                 re-run the configuration wizard
skip | next             skip current song
status | now             show what's playing
rescan                update the database
quit | exit | q          stop and exit
```

## Connecting a player

Point any client that accepts an Icecast/MP3 stream URL at:

```
http://<host-ip>:<port><mount>
```

using the host, port, and mount you set during setup (e.g.
`http://192.168.1.20:8000/stream.mp3`). This works for streaming apps,
browsers, VLC, or a game's internet-radio config (e.g. ETS2's
`live_streams.sii`).
