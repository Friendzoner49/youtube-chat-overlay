<img src="assets/icon.png" alt="" width="120" align="right">

# YouTube Live Chat Overlay

**English** · [Tiếng Việt](README.vi.md)

Turn the live-chat replay of a YouTube stream into a **transparent video of the chat box**, perfectly synced with the stream, so you can stack it on top of your footage in DaVinci Resolve, Premiere Pro, Final Cut, CapCut and other editors.

<br clear="right">

![Chat styles](docs/styles.png)

## Download

Prebuilt, ready-to-run builds (no Python needed) are attached to each [Release](../../releases/latest), built automatically by GitHub Actions:

- **Windows:** `ChatOverlay-windows.zip` → unzip, run `ChatOverlay.exe`.
- **macOS (Apple Silicon):** `ChatOverlay-macos.zip` → unzip, see [macOS Gatekeeper](#macos-standalone-app) below before opening.

Or run from source / build your own (see below) on any platform, including Windows x86/x64, Intel Macs and Linux.

## Features

- **Frame-accurate sync** with the stream, using the timestamps YouTube stores for every message.
- **Messages appear one at a time.** When many people chat in the same instant, messages are queued at least 0.1 s apart (configurable), with a short slide-up animation. A burst is spread evenly around its real time (some messages a fraction of a second early, some late) instead of only being pushed later, and the queue speeds up if it piles up, so the chat stays within about a second of real time.
- **At most N messages on screen** (default 10). Older messages slide out and fade at the top.
- **Three looks:** text-only with an outline, translucent bubbles, or a YouTube-style panel.
- **Supported content:** avatars, YouTube and Unicode emoji, owner, moderator, member and verified badges, Super Chats, Super Stickers and memberships. Deleted messages are skipped.
- **Download the chat straight from a YouTube link**, no command line needed, into a download folder of your choice that the app remembers.
- **Exports just the chat-box area** by default, at native resolution (e.g. 440×866 px for a 1080p video), so files stay small and sharp. Drop the clip into a corner of your timeline.
- **Fast, compact transparent files.** Each distinct frame is compressed once, and repeated frames share the same data inside the MOV. A 90-second 60 fps clip needs 761 compressed frames instead of 5,400.
- **Catches mismatched files.** Before rendering, the app checks that the chat and the video belong to the same stream: the stream date stored in the chat, the dates in both file names (`230917…`, `17⧸09⧸2023`, `2023-09-17`), YouTube IDs in brackets and the chat's length against the video's. If something is off, it explains why and asks before continuing.
- **Render only the part you need** (start/end time). Output files are named after the time range, e.g. `…_chat_overlay_1h02m00s-1h10m00s.mov`.
- **Transparent outputs:** ProRes 4444, FFV1 (lossless), QuickTime Animation and VP9 WebM. Also green-screen MP4, or burning the chat directly into the video (GPU encoding with NVIDIA, Intel, AMD or Apple).
- **Bilingual GUI** (English / Tiếng Việt), plus a full command-line interface.

## Requirements

- **Python 3.8+.** On Windows, use the installer from [python.org](https://www.python.org/downloads/) and tick *“Add python.exe to PATH”*.
- **[FFmpeg](https://ffmpeg.org/download.html)** with `ffmpeg` and `ffprobe` available on your `PATH`. Alternatively, put `ffmpeg.exe` and `ffprobe.exe` next to `chat_overlay.py`.
- **Python packages** from `requirements.txt`: [Pillow](https://python-pillow.org/), and [yt-dlp](https://github.com/yt-dlp/yt-dlp) (only needed for downloading chats from links).

## Getting started

### Windows (no console window)

Double-click **`ChatOverlay.pyw`**.

- On the first run it installs the missing packages automatically.
- No administrator rights are needed.
- `.pyw` files run with `pythonw.exe`, so no black console window appears.

If double-clicking opens the file in a text editor instead: right-click → *Open with* → *Python* (or `pythonw.exe`). To get a desktop shortcut: right-click → *Send to* → *Desktop (create shortcut)*.

### Windows: standalone `.exe`

Build a double-clickable `ChatOverlay.exe` that runs without Python (handy if your Python launcher or `.pyw` association is broken, or to copy the app to another PC):

```bat
pip install -r requirements.txt pyinstaller
python build_exe.py
```

- The result is the folder `ChatOverlay\` (about 50 MB) with `ChatOverlay.exe` inside. Keep the whole folder together; you can move or copy it anywhere.
- FFmpeg is still needed (on `PATH`, or `ffmpeg.exe`/`ffprobe.exe` next to `ChatOverlay.exe`).
- Settings are saved in `settings.json` next to `ChatOverlay.exe`. On the first build they are copied from the script version; rebuilding keeps them.
- yt-dlp is bundled inside the `.exe`. When chat downloads start failing after a YouTube change, run `python build_exe.py` again: it updates yt-dlp before rebuilding.
- The build is a folder rather than a single file, so it starts quickly and never unpacks itself into `%TEMP%`.

### macOS / Linux / manual

```bash
pip install -r requirements.txt
python chat_overlay.py            # opens the GUI
```

On macOS with Homebrew Python, the GUI needs Tk: run `brew install python-tk`. FFmpeg: `brew install ffmpeg`.

### macOS: standalone `.app`

A prebuilt `ChatOverlay.app` (Apple Silicon) is attached to each [Release](../../releases/latest). It is unsigned, so the first launch needs one extra step:

```bash
xattr -dr com.apple.quarantine ChatOverlay.app     # removes the Gatekeeper quarantine flag
```

Or right-click `ChatOverlay.app` → **Open** → confirm in the dialog (only needed once).

To build it yourself instead:

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --windowed --name ChatOverlay --icon assets/icon.png --add-data "assets:assets" chat_overlay.py
```

The result is `dist/ChatOverlay.app`. FFmpeg (`brew install ffmpeg`) is still needed; the app looks for it on `PATH`, falling back to `/opt/homebrew/bin` and `/usr/local/bin` since apps launched from Finder don't inherit a Terminal's `PATH`.

## Using the app

1. **Get the chat.** Either:
   - paste the YouTube link and press **Download chat**, or
   - pick an existing `.live_chat.json` file.

   Downloading does the same as `yt-dlp --write-subs --sub-langs live_chat --skip-download URL`. Use **Chat download folder** to choose where the file is saved; the app remembers it for next time. If you leave it blank, the chat is saved next to the selected video, or in your Downloads folder.

   **Age-restricted or members-only videos** need YouTube login cookies, saved as a `cookies.txt` file in the chat download folder (the app then uses it automatically on every future download):
   - **Without closing the browser:** load the small [`browser-extension/`](browser-extension) included in this repo (`chrome://extensions` → Developer mode → Load unpacked), click its toolbar icon → **Export cookies.txt**, and save it into the chat download folder. It reads cookies through the browser's own official API, the same way an extension like *Get cookies.txt LOCALLY* does — not by touching the browser's cookie file, so the browser can stay open.
   - **With the browser closed:** pick your browser next to **Get cookies** in the app and press it. This reads the browser's cookie database directly, which only works while the browser isn't running — its cookie database is locked while it's open, so the button fails with a "could not copy cookie database" message until you close it completely (including background/tray processes).
2. **(Recommended) Pick the source video.** The app only reads its size, frame rate and length; it does not re-encode it unless you choose *Burn into the source video*. If you don't pick one, fill in *Frame size* and *FPS* yourself, otherwise 1920×1080 at 30 fps is used.
3. **Choose output, style, position**, and optionally a *Start*/*End* time to render only part of the stream.
4. Press **Preview image** to check the look at a given time, then **Export video**.

Settings (language, chat download folder, work folder, style, format, sizes…) are remembered between sessions. They are stored in `settings.json` next to `chat_overlay.py`, so nothing is written to your system drive. Only if that folder is read-only does the app fall back to `%APPDATA%\ChatOverlay\` (Windows) or `~/.config/ChatOverlay/`. Settings saved by older versions in `%APPDATA%` are migrated automatically, then removed.

### Work folder (temp files & caches)

Everything the app writes while processing goes into one **work folder**:

| Subfolder | Contents |
|---|---|
| `temp/` | temporary frames (several GB for long chats, deleted after each export), plus temp files from Python, FFmpeg and yt-dlp |
| `cache/` | downloaded avatars, emoji and badges (reused next time) |
| `yt-dlp-cache/` | yt-dlp's small cache |

By default this is `work/` next to the script (on macOS, a frozen `.app` build defaults to `~/Library/Application Support/ChatOverlay/work` instead, since the bundle itself shouldn't be written to). To keep your system drive (e.g. `C:`) free, pick a folder on another fast drive in **Work folder (temp files + cache)**, e.g. `D:\LivechatTemp`. It is remembered. The old `chat_cache/` folder from previous versions is moved there automatically.

When it installs packages on first run, the Windows launcher also uses this folder for temp files and runs pip without its download cache. The Python packages themselves still live wherever Python is installed.

### Typical workflow for long streams

If you cut highlights from a multi-hour stream, render the chat **only for each highlight**:

1. Set *Start* and *End* to the highlight's position in the original stream, e.g. `1:02:00` → `1:10:00`.
2. Export.
3. In your editor, put the overlay on the track above the matching clip, starting at the same frame. The file name tells you which range it covers.

Rendering whole multi-hour streams as a transparent intra-frame video takes a lot of disk space (see below).

## Which output format?

| Output | Transparent | Size (chat box, 1080p 60 fps, busy chat, per minute) | Best for |
|---|---|---|---|
| **ProRes 4444 XQ** (`prores`, default) | yes | ~130 MB | **DaVinci Resolve** and any other editor; the safest choice |
| **FFV1 lossless** (`ffv1`) | yes | ~50 MB | DaVinci Resolve (FFV1 RGBA is listed as supported by Blackmagic). Pixel-exact and smaller; test it once |
| **QuickTime Animation** (`mov`) | yes | ~100 MB | Premiere Pro, After Effects, Final Cut. DaVinci reads it **without** transparency |
| **VP9 WebM** (`webm`) | yes | ~6 MB | OBS, browsers |
| **Green-screen MP4** (`green`) | via chroma key | small | any editor (GPU encoding) |
| **Burn-in MP4** (`burn`) | — | ≈ source | a finished video in one step (GPU encoding) |

Sizes were measured on a real chat and depend on how busy it is: quiet stretches cost almost nothing.

**Why the GPU isn't used for transparent files:** GPU encoders (NVIDIA NVENC, Intel Quick Sync, AMD AMF) only produce H.264/HEVC/AV1 *without* an alpha channel. Every transparent format that editors such as DaVinci read (ProRes 4444, FFV1, DNxHR 444) is encoded on the CPU. The app compensates by rendering frames on all CPU cores, compressing each distinct frame only once, and exporting only the chat-box area. The GPU is used for the green-screen and burn-in outputs.

### Placing the overlay in DaVinci Resolve

After an export, the log prints something like:

```
DaVinci: Inspector → Retime and Scaling → Scaling = Crop (keeps 1:1 pixels, sharpest),
         then Transform → Position X = -700, Y = -67 (timeline 1920x1080) to place it where you chose
```

1. Put the overlay on the track above your clip, starting at the matching frame.
2. In the **Inspector**, set **Retime and Scaling → Scaling** to **Crop**. Otherwise DaVinci scales the small clip up to fill the frame, which makes the text blurry.
3. Enter the printed **Position X/Y** under **Transform**. The chat then lands exactly at the position and margins you chose in the app. The values assume the timeline has the same resolution as your source video.

If DaVinci (or another editor) has trouble reading a file, untick **Share identical frames** (or use `--no-share`). Files get larger, but the frames are identical.

## Command line

```bash
# ProRes overlay for 1:02:00–1:10:00, size/fps taken from the source video
python chat_overlay.py stream.live_chat.json --video stream.mp4 --format prores --start 1:02:00 --end 1:10:00

# Download the chat from a link, then render
python chat_overlay.py "https://www.youtube.com/watch?v=VIDEO_ID" --video stream.mp4 --format ffv1

# Preview a single frame at 25:30
python chat_overlay.py stream.live_chat.json --video stream.mp4 --preview 25:30

# Burn the chat into the video with the GPU
python chat_overlay.py stream.live_chat.json --video stream.mp4 --format burn --encoder hevc_nvenc
```

Run `python chat_overlay.py --help` for all options:

- Style: `--style`, `--position`, `--margin-x`, `--margin-y`, `--box-width`, `--font-size`.
- Message flow: `--max-messages`, `--min-gap`, `--anim`, `--hide-after`.
- Timing: `--offset`.
- Safety: `--ignore-mismatch` renders even if the chat and the video look like different streams (by default the command stops and explains why).
- Output: `--format` (default `prores`), `--canvas box|full` (default `box`: only the chat-box area), `--no-share` (encode every frame instead of sharing identical ones), `--lang`.
- Folders: `--work-dir` (default: the folder saved by the GUI, else `./work`). `--temp-dir` and `--cache-dir` override single subfolders.
- Chat download: `--download-dir`. When a link is given without it, the folder remembered by the GUI is used, then the video's folder, then the current folder.

## Customising the position

Pick one of six positions in the GUI, then fine-tune the distance to the frame edges in `chat_overlay.py`, inside `class Options`:

```python
margin_x: int = 40   # left/right, px at 1080p (scaled automatically for 1440p/4K)
margin_y: int = 40   # top/bottom – lower this to move a bottom-anchored chat further down
```

Or from the command line: `--margin-x 30 --margin-y 10`. With the default chat-box-only export, these margins are also used to compute the DaVinci *Position X/Y* printed in the log. You can always move the clip freely in your editor afterwards.

## Tips & troubleshooting

- **“ffmpeg not found”**: install FFmpeg and add its `bin` folder to `PATH`, or copy `ffmpeg.exe` and `ffprobe.exe` next to the script.
- **Double-clicking `ChatOverlay.pyw` shows "Activation is blocked due to the .appinstaller update settings"** (or hangs on "Hang on while we get your app's information"): `.pyw` files are opened by the *Python Install Manager* app, which Windows blocks when a newer version is available but can't be installed automatically. Update it manually in PowerShell with `Add-AppxPackage -AppInstallerFile https://www.python.org/ftp/python/pymanager/pymanager.appinstaller` (if it says the app is in use, end `pyshellext.exe` in Task Manager and run it again). Your installed Python versions and packages are kept. Or skip the install manager entirely: right-click the desktop → *New → Shortcut*, enter `"<path to>\pythonw.exe" "<path to>\ChatOverlay.pyw"` (`pythonw.exe` is usually in `%LOCALAPPDATA%\Python\pythoncore-3.xx-64\`), and launch the app from that shortcut.
- **Chat download fails**: YouTube changes often, so update yt-dlp with `pip install -U yt-dlp` (or rebuild the `.exe`/`.app`). Only past livestreams with chat replay enabled have a chat to download. Age-restricted or members-only streams need a `cookies.txt` file — see [Using the app](#using-the-app) above.
- **Connection drops while downloading the chat** (e.g. `SSL: UNEXPECTED_EOF_WHILE_READING`): long chats need hundreds of requests in a row, so a brief network hiccup is common. The app retries each request up to 10 times, and if that isn't enough it re-fetches the same part up to 3 more rounds, so it continues where it stopped instead of starting over. The log shows a `⚠ Connection lost…` line when this happens. If it still fails, check your network and try disabling VPN or your antivirus's HTTPS scanning.
- **Disk space**: the distinct frames are rendered to a temporary folder before encoding, roughly 1–1.5 GB per hour of chat at 1080p and more at 1440p. Point the *Work folder* to a drive with free space. Setting *Slide animation* to `0` cuts the number of frames about sixfold; messages still appear one by one.
- **Fonts**: Segoe UI / Arial / Roboto / Noto Sans / DejaVu are detected automatically. To use your own, drop `Roboto-Regular.ttf` and `Roboto-Medium.ttf` (or Noto Sans) into a `fonts/` folder next to the script, or use `--font` and `--font-bold`.
- **Avatars and emoji** are downloaded once and cached in `<work folder>/cache/`.
- **Chat reacts a few seconds after the action**: each message keeps the exact time it reached YouTube, the same as YouTube's own chat replay. Viewers watched the stream with a few seconds of latency before typing, so reactions naturally arrive late. Set *Time offset* to a negative value (for example `-3` to `-8`, or `--offset -5`) to show every message earlier.
- **Blurry chat in DaVinci**: set *Scaling = Crop* on the clip (see “Placing the overlay in DaVinci Resolve”).
- **“Permission denied” when saving**: a bare file name in *Save as* is saved next to the chat file. Check that the target folder is writable and the output file isn't open in your editor (e.g. DaVinci).

## How it works (short version)

1. Messages are read from the yt-dlp JSON (`videoOffsetTimeMsec`) and queued so that each appears at least `min_gap` after the previous one.
2. Each message is drawn once with Pillow.
3. Only the frames where the chat actually changes are rendered, in parallel on all CPU cores.
4. FFmpeg compresses each distinct frame once, as an image sequence at the exact frame rate.
5. The app rewrites the MOV sample table so every output frame points at the right compressed frame. Repeated frames share data, and the result is a normal constant-frame-rate MOV. Other formats are converted from a lossless intermediate built the same way.

This keeps rendering fast even for multi-hour streams. In testing, all eight output types had exactly the expected number of frames, and every sampled frame (including mid-animation frames at 60 fps) showed the expected chat state at the right time.

## License

[MIT](LICENSE).

Third-party tools used at runtime, not bundled:
- [FFmpeg](https://ffmpeg.org/legal.html) (LGPL/GPL)
- [Pillow](https://github.com/python-pillow/Pillow/blob/main/LICENSE) (MIT-CMU)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE) (Unlicense)

Please respect YouTube's Terms of Service and the privacy of your viewers when publishing chat content.
