#!/usr/bin/env python3
import subprocess

CODEC_EXTS = (
    "flac", "m4a", "wav", "mp3", "mp4",
    "aac", "ogg", "opus", "wma", "alac",
    "mkv", "webm", "avi", "mov", "flv",
)

def get_ext(url: str):
    path = url.split("?")[0].split("#")[0]
    for ext in CODEC_EXTS:
        if path.lower().endswith("." + ext):
            return ext
    return None

def main():
    links = []
    print("Enter links one per line. Type 'start' to begin downloading.")
    while True:
        inp = input("Link: ").strip()
        if inp.lower() == "start":
            break
        if inp:
            links.append(inp)

    for k, url in enumerate(links):
        ext = get_ext(url)
        if ext:
            subprocess.run(["aria2c", "-x", "8", "-s", "8", "-o", f"{k}.{ext}", url])
        else:
            subprocess.run(["yt-dlp", "-o", "%(title)s.%(ext)s", url])

if __name__ == "__main__":
    main()