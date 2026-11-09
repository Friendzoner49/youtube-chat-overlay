#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Live Chat Overlay — chat_overlay.py

Turns a YouTube live-chat replay (yt-dlp .live_chat.json, or a YouTube link) into a
transparent video of the chat box, synced to the original stream, ready to stack on
top of your footage in DaVinci Resolve / Premiere / Final Cut / CapCut…

Biến live chat của YouTube (file .live_chat.json của yt-dlp, hoặc link YouTube) thành
video khung chat nền trong suốt, khớp thời gian với buổi live, để lồng vào video.

  python chat_overlay.py                                   -> GUI / giao diện
  python chat_overlay.py chat.live_chat.json --format prores --start 1:02:00 --end 1:10:00
  python chat_overlay.py "https://www.youtube.com/watch?v=..." --video stream.mp4
  python chat_overlay.py --help

Requires / Cần: Python 3.8+, Pillow, ffmpeg + ffprobe; yt-dlp (optional, for links).
"""
import argparse
import bisect
import colorsys
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unicodedata
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont
except ImportError:
    sys.stderr.write("Thiếu thư viện Pillow. Hãy chạy: pip install pillow\n")
    sys.exit(1)

APP_TITLE = "YouTube Live Chat → Video Overlay"
RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS
# Bản .exe (PyInstaller): settings.json, fonts/, ffmpeg nằm cạnh file .exe chứ không phải trong thư mục giải nén.
# Frozen .exe (PyInstaller): settings.json, fonts/, ffmpeg live next to the .exe, not in the bundle folder.
FROZEN = getattr(sys, "frozen", False)
SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
WIN_FONTS = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")


class Cancelled(Exception):
    pass


class PairMismatch(RuntimeError):
    """File chat và video có vẻ không cùng một buổi live. / Chat and video look like different streams."""


# ----------------------------------------------------------------------------- i18n
LANG = "en"
LANG_NAMES = {"vi": "Tiếng Việt", "en": "English"}
STRINGS = {
    # ---- log / errors
    "skip_bad": ("  ! Bỏ qua {n} dòng JSON bị lỗi", "  ! Skipped {n} malformed JSON lines"),
    "no_offset": ("  ! {n} tin không có videoOffsetTimeMsec – dùng timestampUsec thay thế",
                  "  ! {n} messages have no videoOffsetTimeMsec – using timestampUsec instead"),
    "no_font": ("  ! Không tìm thấy font hệ thống – chữ có dấu có thể lỗi. Dùng --font để chỉ định file .ttf",
                "  ! No system font found – accented characters may break. Use --font to pick a .ttf file"),
    "no_net": ("  ! Không tải được ảnh (mất mạng?) – dùng avatar chữ cái và emoji dự phòng",
               "  ! Could not download images (offline?) – using letter avatars and fallback emoji"),
    "ffprobe_fail": ("ffprobe không đọc được video: ", "ffprobe could not read the video: "),
    "ffmpeg_fail": ("ffmpeg báo lỗi:\n", "ffmpeg failed:\n"),
    "enc_na": ("  ! Máy này không dùng được bộ mã hoá {e} – chuyển sang tự động chọn",
               "  ! Encoder {e} is not available on this machine – picking one automatically"),
    "no_chat": ("Không tìm thấy file chat JSON.", "Chat JSON file not found."),
    "no_ffmpeg": ("Không tìm thấy ffmpeg. Cài ffmpeg (https://ffmpeg.org) và thêm vào PATH, "
                  "hoặc đặt ffmpeg.exe cạnh file chat_overlay.py.",
                  "ffmpeg not found. Install ffmpeg (https://ffmpeg.org) and add it to PATH, "
                  "or put ffmpeg.exe next to chat_overlay.py."),
    "burn_video": ("Chế độ 'ghép thẳng vào video' cần chọn file video.", "'Burn into video' mode needs a video file."),
    "s_read": ("1) Đọc file chat…", "1) Reading chat file…"),
    "no_msgs": ("File không có tin nhắn chat nào đọc được.", "No readable chat messages in this file."),
    "n_msgs": ("   {n} tin ({kinds})", "   {n} messages ({kinds})"),
    "n_removed": (", đã bỏ {n} tin bị xoá", ", {n} deleted messages removed"),
    "no_video": ("Không tìm thấy file video.", "Video file not found."),
    "mm_head": ("File chat và video có vẻ KHÔNG cùng một buổi live:",
                "The chat file and the video do not seem to be from the same stream:"),
    "mm_len": ("• Tin chat cuối ở mốc {c}, nhưng video chỉ dài {v}.",
               "• The last chat message is at {c}, but the video is only {v} long."),
    "mm_short": ("• Chat kết thúc ở mốc {c} nhưng video dài {v} (chat chỉ phủ {p}% video).",
                 "• The chat ends at {c} but the video is {v} long (chat covers only {p}% of it)."),
    "mm_date_v": ("• Chat là của buổi live bắt đầu lúc {c} (giờ máy này), nhưng tên video ghi ngày {n}.",
                  "• The chat is from a stream that started at {c} (this PC's time), but the video name says {n}."),
    "mm_date_c": ("• Chat là của buổi live bắt đầu lúc {c} (giờ máy này), nhưng tên file chat ghi ngày {n}.",
                  "• The chat is from a stream that started at {c} (this PC's time), but the chat file name says {n}."),
    "mm_name": ("• Tên file chat ghi ngày {a}, tên video ghi ngày {b}.",
                "• The chat file name says {a}, the video name says {b}."),
    "mm_id": ("• Mã video YouTube trong tên file khác nhau: chat [{a}], video [{b}].",
              "• Different YouTube video IDs in the file names: chat [{a}], video [{b}]."),
    "mm_ask": ("Vẫn tiếp tục xuất?", "Continue anyway?"),
    "mm_cli": ("Nếu chắc chắn đúng cặp file, chạy lại với --ignore-mismatch.",
               "If you are sure the files belong together, run again with --ignore-mismatch."),
    "video_info": ("   Video: {w}x{h}, {fps:.3f} fps, dài {dur}", "   Video: {w}x{h}, {fps:.3f} fps, length {dur}"),
    "no_ffprobe": ("  ! Không có ffprobe – dùng kích thước mặc định", "  ! ffprobe not found – using the default size"),
    "queued": ("   Xếp hàng xong: tối đa {m} tin/khung, mỗi tin cách nhau ≥ {g:.2f}s, lệch lớn nhất do dồn tin: "
               "muộn {lag:.2f}s / sớm {early:.2f}s",
               "   Queued: up to {m} messages on screen, ≥ {g:.2f}s apart, max shift caused by bursts: "
               "late {lag:.2f}s / early {early:.2f}s"),
    "s_assets": ("2) Tải avatar / emoji…", "2) Fetching avatars / emoji…"),
    "assets": ("   Ảnh sẵn sàng: {a}/{b}", "   Images ready: {a}/{b}"),
    "s_layout": ("3) Dàn trang tin nhắn…", "3) Laying out messages…"),
    "box": ("   Khung chat {bw}x{bh}px tại ({x},{y}) trên khung hình {cw}x{ch}",
            "   Chat box {bw}x{bh}px at ({x},{y}) on a {cw}x{ch} frame"),
    "prev_saved": ("Đã lưu ảnh xem thử: {p}", "Preview saved: {p}"),
    "s_frames": ("4) Dựng khung hình: {a} → {b} ({n} frame @ {fps}fps)…", "4) Rendering frames: {a} → {b} ({n} frames @ {fps}fps)…"),
    "temp": ("   Thư mục tạm: {p} (còn trống {gb:.0f} GB)", "   Temp folder: {p} ({gb:.0f} GB free)"),
    "uniq": ("   {n} khung hình khác nhau", "   {n} unique frames"),
    "encoder": ("   Bộ mã hoá: {e}", "   Encoder: {e}"),
    "enc_cpu": ("  (CPU – sẽ chậm với video dài)", "  (CPU – slow for long videos)"),
    "s_encode": ("5) Mã hoá video bằng ffmpeg…", "5) Encoding video with ffmpeg…"),
    "done": ("XONG ✔  {p}  ({mb:.1f} MB, mất {s:.0f}s)", "DONE ✔  {p}  ({mb:.1f} MB, took {s:.0f}s)"),
    "start_note": ("   Lưu ý: file này bắt đầu từ mốc {t} của buổi live – đặt nó khớp với đoạn video tương ứng.",
                   "   Note: this file starts at {t} of the stream – line it up with the matching part of your footage."),
    "no_tk": ("Máy không có tkinter – hãy dùng dòng lệnh: python chat_overlay.py --help",
              "tkinter is not available – use the command line: python chat_overlay.py --help"),
    "cancelled": ("Đã huỷ.", "Cancelled."),
    "error": ("LỖI:", "ERROR:"),
    # ---- chat download
    "dl_start": ("Đang tải live chat từ YouTube: {url}", "Downloading live chat from YouTube: {url}"),
    "dl_done": ("Đã tải xong chat: {p} ({mb:.1f} MB)", "Live chat downloaded: {p} ({mb:.1f} MB)"),
    "dl_nochat": ("Video này không có live chat replay (chỉ có ở video đã từng livestream và còn bật chat replay).",
                  "This video has no live chat replay (only past livestreams with chat replay enabled have one)."),
    "dl_noytdlp": ("Chưa có yt-dlp. Cài bằng lệnh: pip install yt-dlp", "yt-dlp is not installed. Install it with: pip install yt-dlp"),
    "dl_fail": ("Tải chat thất bại: {e}\n(Nếu YouTube vừa thay đổi, thử cập nhật: {upd})",
                "Chat download failed: {e}\n(If YouTube changed something, try updating: {upd})"),
    "upd_pip": ("pip install -U yt-dlp", "pip install -U yt-dlp"),
    "upd_exe": ("chạy lại build_exe.py để build .exe với yt-dlp mới",
                "re-run build_exe.py to rebuild the .exe with a newer yt-dlp"),
    "dl_retry": ("   ⚠ Mất kết nối khi tải đoạn chat #{i} ({e}) – thử lại lần {n}/{m} sau {s}s…",
                 "   ⚠ Connection lost on chat part #{i} ({e}) – retry {n}/{m} in {s}s…"),
    "dl_cookiefile": ("   Dùng cookies từ: {p}", "   Using cookies from: {p}"),
    "dl_cookie_fail": ("   ⚠ Không lấy được cookies từ Chrome ({e}) – có thể do Chrome đang chạy (khoá file "
                       "cookie). Hãy đóng hẳn Chrome (kể cả tiến trình nền) rồi thử lại nếu video cần đăng nhập. "
                       "Đang thử tải tiếp không dùng cookies…",
                       "   ⚠ Could not read cookies from Chrome ({e}) – Chrome may be running and locking the "
                       "cookie file. Close Chrome completely (including background processes) and retry if the "
                       "video requires login. Retrying without cookies…"),
    "ck_start": ("Đang đọc cookies từ {b}… (hãy đóng hẳn trình duyệt nếu bị lỗi)",
                 "Reading cookies from {b}… (close the browser completely if this fails)"),
    "ck_none": ("Không tìm thấy cookie nào của youtube.com/google.com trong {b}. Hãy đăng nhập YouTube trong "
                "trình duyệt đó rồi thử lại.",
                "No youtube.com/google.com cookies found in {b}. Log in to YouTube in that browser and try again."),
    "ck_done": ("Đã lưu {n} cookie vào: {p}", "Saved {n} cookies to: {p}"),
    "ck_ext_done": ("Đã lấy {n} cookie qua tiện ích mở rộng (không cần đóng trình duyệt), lưu vào: {p}",
                    "Got {n} cookies via the browser extension (no need to close the browser), saved to: {p}"),
    "ck_fail": ("Lấy cookies thất bại: {e}", "Failed to read cookies: {e}"),
    "dl_net": ("Mất kết nối tới YouTube nhiều lần liên tiếp nên không tải tiếp được ({e}).\n"
               "Hãy kiểm tra mạng, tắt thử VPN / tính năng quét HTTPS của phần mềm diệt virus, rồi bấm Tải chat lại.",
               "The connection to YouTube kept dropping, so the download could not continue ({e}).\n"
               "Check your network, try disabling VPN / your antivirus's HTTPS scanning, then press Download chat again."),
    "dl_playlist": ("Hãy dán link của một video cụ thể, không phải playlist/kênh.",
                    "Please paste the link of a single video, not a playlist or channel."),
    # ---- GUI
    "g_url": ("Link YouTube", "YouTube link"),
    "g_dl": ("Tải chat", "Download chat"),
    "g_chat": ("File chat (.json)", "Chat file (.json)"),
    "g_video": ("Video gốc (tuỳ chọn)", "Source video (optional)"),
    "g_out": ("Lưu thành (tên file hoặc thư mục; trống = tự đặt)", "Save as (file name or folder; blank = auto)"),
    "no_write": ("Không ghi được vào thư mục: {p}\n({e})\nHãy chọn thư mục khác ở ô 'Lưu thành'.",
                 "Cannot write to folder: {p}\n({e})\nPlease choose another folder in 'Save as'."),
    "file_locked": ("File đích đang bị chương trình khác mở (ví dụ DaVinci): {p}\nHãy đóng nó hoặc đặt tên khác.",
                    "The output file is open in another program (e.g. DaVinci): {p}\nClose it or pick another name."),
    "workers": ("   Dựng khung hình song song trên {n} nhân CPU", "   Rendering frames in parallel on {n} CPU cores"),
    "workers_fail": ("  ! Không chạy song song được ({e}) – dựng tuần tự", "  ! Parallel rendering unavailable ({e}) – rendering sequentially"),
    "smart": ("   Chỉ nén {u} khung khác nhau thay vì {n} khung (nhanh hơn ~{x:.0f} lần), rồi ghép thành MOV đủ khung",
              "   Encoding only {u} distinct frames instead of {n} (~{x:.0f}x less work), then building a full-length MOV"),
    "assemble": ("   Ghép MOV hoàn chỉnh…", "   Building the final MOV…"),
    "ph_assemble": ("Đang ghép MOV", "Building MOV"),
    "out_path": ("   Lưu thành: {p}", "   Output: {p}"),
    "g_dldir": ("Thư mục lưu chat tải về (trống = mặc định)", "Chat download folder (blank = default)"),
    "dl_folder": ("   Lưu vào thư mục: {p}", "   Saving to folder: {p}"),
    "g_work": ("Thư mục làm việc (file tạm + cache)", "Work folder (temp files + cache)"),
    "work": ("   Thư mục làm việc: {p} (còn trống {gb:.0f} GB)", "   Work folder: {p} ({gb:.0f} GB free)"),
    "no_work": ("Không dùng được thư mục làm việc: {p}\n({e})\nKiểm tra ổ đĩa còn cắm/còn chỗ, hoặc chọn thư mục khác.",
                "Cannot use the work folder: {p}\n({e})\nCheck that the drive is connected and has space, or pick another folder."),
    "cache_moved": ("   Đã chuyển cache ảnh cũ sang: {p}", "   Moved the old image cache to: {p}"),
    "g_browse": ("Chọn…", "Browse…"),
    "g_browser": ("Trình duyệt", "Browser"),
    "g_ck_btn": ("Lấy cookies", "Get cookies"),
    "g_ck_ok": ("Đã lưu cookies vào: {p}", "Cookies saved to: {p}"),
    "g_fmt": ("Kiểu xuất", "Output"),
    "g_style": ("Giao diện chat", "Chat style"),
    "g_pos": ("Vị trí khung chat", "Chat position"),
    "g_enc": ("Mã hoá (ghép thẳng / phông xanh)", "Encoder (burn-in / green screen)"),
    "g_avatars": ("Hiện avatar", "Show avatars"),
    "g_share": ("Dùng chung khung trùng (nhanh, file nhẹ – tắt nếu phần mềm dựng đọc file bị lỗi)",
                "Share identical frames (fast, small files – untick if your editor has trouble reading the file)"),
    "davinci": ("   DaVinci: Inspector → Retime and Scaling → Scaling = Crop (giữ nguyên kích thước, nét 1:1),\n"
                "            rồi Transform → Position X = {x}, Y = {y} (timeline {cw}x{ch}) để đặt đúng vị trí đã chọn",
                "   DaVinci: Inspector → Retime and Scaling → Scaling = Crop (keeps 1:1 pixels, sharpest),\n"
                "            then Transform → Position X = {x}, Y = {y} (timeline {cw}x{ch}) to place it where you chose"),
    "g_canvas": ("Chỉ xuất đúng vùng khung chat (nhẹ, nhanh – khuyên dùng)",
                 "Export only the chat box area (smaller, faster – recommended)"),
    "g_prev_at": ("Xem thử tại", "Preview at"),
    "g_prev": ("Xem thử ảnh", "Preview image"),
    "g_run": ("▶ Xuất video", "▶ Export video"),
    "g_cancel": ("Huỷ", "Cancel"),
    "g_ready": ("Chọn file chat hoặc dán link YouTube để bắt đầu.", "Pick a chat file or paste a YouTube link to start."),
    "g_err_num": ("Có ô số nhập sai định dạng: {f}", "Invalid value in field: {f}"),
    "g_err_chat": ("Hãy chọn file chat .json (hoặc tải từ link YouTube).", "Please pick a chat .json file (or download one from a YouTube link)."),
    "g_err_burn": ("Chế độ ghép thẳng cần chọn file video gốc.", "Burn-in mode needs the source video file."),
    "g_err_prev": ("Thời điểm xem thử không hợp lệ.", "Invalid preview time."),
    "g_err_url": ("Hãy dán một link YouTube hợp lệ (https://…).", "Please paste a valid YouTube link (https://…)."),
    "g_done": ("Hoàn tất: {p}", "Finished: {p}"),
    "g_open": ("Đã xuất xong:\n{p}\n\nMở thư mục chứa file?", "Export finished:\n{p}\n\nOpen the containing folder?"),
    "g_chat_ok": ("Đã tải chat và chọn sẵn file: {p}", "Chat downloaded and selected: {p}"),
    "g_err": ("Lỗi – xem chi tiết bên dưới.", "Error – see details below."),
    "ph_download": ("Đang tải ảnh", "Downloading images"),
    "ph_layout": ("Đang dàn trang", "Laying out"),
    "ph_frames": ("Đang dựng khung hình", "Rendering frames"),
    "ph_encode": ("Đang mã hoá video", "Encoding video"),
    "ph_chat": ("Đang tải chat… {mb:.1f} MB", "Downloading chat… {mb:.1f} MB"),
    # ---- video download tab
    "g_tab_chat": ("Khung chat", "Chat overlay"),
    "g_tab_video": ("Tải video", "Download video"),
    "gv_hint": ("Dán link YouTube, bấm Kiểm tra định dạng để xem video đã tải được chưa (livestream vừa xong có thể chưa có), "
                "rồi bấm Tải video. Có bản Premium thì lấy bản đó rồi đổi sang H.264 (_final.mp4) như VP9; không thì AV1 nét nhất; không có AV1 thì "
                "VP9 nét nhất rồi đổi sang H.264 (_final.mp4) để dùng trong DaVinci/Premiere. Chỉ lấy tiếng thì được file m4a gốc, không đổi mã.",
                "Paste a YouTube link, press Check formats to see whether it can be downloaded yet (a just-ended stream may not be), "
                "then press Download video. A Premium format is taken and converted to H.264 (_final.mp4) like VP9; otherwise the sharpest AV1; without AV1, "
                "the sharpest VP9, converted to H.264 (_final.mp4) for DaVinci/Premiere. Audio only gives the original m4a, not re-encoded."),
    "gv_go": ("▶ Tải video", "▶ Download video"),
    "gv_dir": ("Thư mục lưu video (trống = Downloads)", "Video folder (blank = Downloads)"),
    "gv_maxh": ("Độ phân giải tối đa", "Max resolution"),
    "gv_del": ("Xoá file VP9 gốc sau khi đổi xong (giữ lại mỗi file _final.mp4)",
               "Delete the VP9 source after converting (keep only the _final.mp4)"),
    "gv_ready": ("Dán link YouTube, bấm Kiểm tra định dạng, rồi bấm Tải video.",
                 "Paste a YouTube link, press Check formats, then press Download video."),
    "gv_check": ("Kiểm tra định dạng", "Check formats"),
    "vc_have": ("Đang có (hình): {s}", "Available (video): {s}"),
    "vc_ifnow": ("Nếu bấm Tải video bây giờ:", "If you press Download video now:"),
    "vc_ok_av1": ("✔ Đã có AV1 ({v}) – bấm Tải video được rồi.", "✔ AV1 is ready ({v}) – you can press Download video."),
    "vc_no_av1": ("Chưa có AV1, mới có {v}. Tải luôn được, hoặc đợi rồi kiểm tra lại.",
                  "No AV1 yet, only {v}. Download now, or wait and check again."),
    "vc_ok_audio": ("✔ Đã có tiếng – bấm Tải video được rồi.", "✔ Audio is ready – you can press Download video."),
    "vc_none": ("✘ Chưa có định dạng nào. Live vừa xong thì YouTube đang xử lý – đợi rồi kiểm tra lại.",
                "✘ No formats yet. A just-ended stream is still processing – wait and check again."),
    "vc_live": ("✘ Video đang phát trực tiếp – đợi buổi live kết thúc rồi kiểm tra lại.",
                "✘ This video is live right now – wait until the stream ends, then check again."),
    "vc_upcoming": ("✘ Buổi live chưa bắt đầu – chưa có định dạng nào.", "✘ The stream has not started yet – no formats."),
    "vc_post_live": ("  ! Buổi live vừa kết thúc, YouTube vẫn đang xử lý bản ghi: bản nét nhất/AV1 có thể chưa có. Nên đợi rồi kiểm tra lại.",
                     "  ! The stream just ended and YouTube is still processing it: the sharpest/AV1 formats may be missing. Wait and check again."),
    "vc_hls": ("  ! Hiện chỉ có dạng phát trực tiếp (m3u8) – tải chậm hơn; YouTube xử lý xong sẽ có bản tải thẳng.",
               "  ! Only the live-stream form (m3u8) exists for now – slower to download; a direct download appears once YouTube finishes."),
    "gv_done": ("Hoàn tất: {p}", "Finished: {p}"),
    "gv_open": ("Đã tải xong:\n{p}\n\nMở thư mục chứa file?", "Download finished:\n{p}\n\nOpen the containing folder?"),
    "ph_vlist": ("Đang đọc danh sách định dạng", "Reading the format list"),
    "ph_vdl": ("Đang tải video", "Downloading video"),
    "ph_vmerge": ("Đang ghép hình và tiếng", "Merging video and audio"),
    "vd_listing": ("Đang lấy danh sách định dạng (yt-dlp --list-formats)…", "Getting the format list (yt-dlp --list-formats)…"),
    "vd_noformat": ("YouTube không trả về định dạng nào tải được (video riêng tư, giới hạn tuổi/hội viên, hoặc có bản quyền). "
                    "Thử bấm 'Lấy cookies' rồi tải lại.",
                    "YouTube returned no downloadable format (private, age-restricted/members-only or DRM). "
                    "Try 'Get cookies' and download again."),
    "vd_live": ("Video này đang phát trực tiếp – hãy đợi buổi live kết thúc rồi tải.",
                "This video is live right now – wait until the stream ends, then download."),
    "vd_av1_lower": ("   Có AV1 nhưng thấp hơn VP9 ({a} so với {v}) → chọn VP9 để giữ độ nét.",
                     "   AV1 exists but is lower quality than VP9 ({a} vs {v}) → using VP9 to keep the sharpness."),
    "vd_pick_av1": ("▶ Chọn AV1: {v} + tiếng {a} → ghép lại, giữ nguyên.", "▶ Picked AV1: {v} + audio {a} → merged, kept as is."),
    "vd_pick_vp9": ("▶ Không có AV1 phù hợp, chọn VP9: {v} + tiếng {a} → sẽ đổi sang H.264.",
                    "▶ No suitable AV1, picked VP9: {v} + audio {a} → will be converted to H.264."),
    "vd_pick_h264": ("▶ Không có AV1/VP9, chọn H.264: {v} + tiếng {a} → ghép lại, không đổi mã.",
                     "▶ No AV1/VP9, picked H.264: {v} + audio {a} → merged, not re-encoded."),
    "vd_downloaded": ("Đã tải xong: {p} ({mb:.0f} MB)", "Downloaded: {p} ({mb:.0f} MB)"),
    "vd_nofile": ("Tải xong nhưng không thấy file video.", "The download finished but the video file was not found."),
    "vd_conv": ("Đổi sang H.264 bằng {e} → {p}", "Converting to H.264 with {e} → {p}"),
    "vd_conv_cpu": ("  ! Máy không có card NVIDIA dùng được NVENC – đổi bằng CPU (chậm hơn nhiều).",
                    "  ! No usable NVIDIA NVENC on this machine – converting on the CPU (much slower)."),
    "vd_final": ("XONG ✔  {p}  ({mb:.0f} MB)", "DONE ✔  {p}  ({mb:.0f} MB)"),
    "vd_src_deleted": ("   Đã xoá file gốc: {p}", "   Deleted the source file: {p}"),
    "vd_net": ("Mất kết nối tới YouTube nên chưa tải xong ({e}).\nPhần đã tải được giữ lại: bấm Tải video lần nữa "
               "để tải tiếp từ chỗ dừng (nếu dùng VPN, kiểm tra VPN trước).",
               "The connection to YouTube dropped before the download finished ({e}).\nThe part already downloaded is kept: "
               "press Download video again to continue where it stopped (if you use a VPN, check it first)."),
    "upd_app": ("bấm 'Kiểm tra cập nhật yt-dlp' ở tab Tải video", "press 'Check for yt-dlp update' in the Download video tab"),
    "gv_kind": ("Tải gì", "Download"),
    "gv_ytver": ("yt-dlp đang dùng: {v}", "yt-dlp in use: {v}"),
    "gv_upd": ("Kiểm tra cập nhật yt-dlp", "Check for yt-dlp update"),
    "vd_pick_video": ("▶ Chỉ hình: {v} → {k}", "▶ Video only: {v} → {k}"),
    "vd_pick_premium": ("▶ Có bản Premium, chọn: {v} + tiếng {a} → sẽ đổi sang H.264 (_final.mp4) cho DaVinci.",
                        "▶ Premium format found, picked: {v} + audio {a} → will be converted to H.264 (_final.mp4) for DaVinci."),
    "vd_prem_fail": ("  ! Không tải được bản Premium ({e}) – có thể cần cookies tài khoản YouTube Premium. Chuyển sang bản thường…",
                     "  ! Could not download the Premium format ({e}) – it may need YouTube Premium cookies. Using a normal format…"),
    "vc_ok_premium": ("✔ Có bản Premium ({v}) – bấm Tải video sẽ lấy bản này rồi đổi sang H.264.",
                      "✔ Premium format available ({v}) – Download video takes it, then converts to H.264."),
    "vd_keep": ("giữ nguyên, không đổi mã", "kept as is, not re-encoded"),
    "vd_will_conv": ("sẽ đổi sang H.264 (_final.mp4)", "will be converted to H.264 (_final.mp4)"),
    "vd_noaudio": ("(không tiếng)", "(no audio)"),
    "vd_pick_audio": ("▶ Chỉ tiếng: {a} → giữ nguyên chất lượng gốc, không đổi mã.",
                      "▶ Audio only: {a} → original quality, not re-encoded."),
    "vd_audio_noaac": ("  ! Video này không có bản m4a (AAC) – lấy bản tiếng tốt nhất còn lại; phần mềm dựng có thể không đọc được.",
                       "  ! This video has no m4a (AAC) track – using the best other audio; some editors may not read it."),
    "yu_checking": ("Đang kiểm tra bản yt-dlp mới…", "Checking for a newer yt-dlp…"),
    "yu_new": ("Có yt-dlp mới: {new} (đang dùng {cur}).\nYouTube hay thay đổi nên bản mới giúp tải ổn định hơn.\n\nCập nhật bây giờ?",
               "A newer yt-dlp is available: {new} (you have {cur}).\nYouTube changes often, so a newer one keeps downloads working.\n\nUpdate now?"),
    "yu_latest": ("yt-dlp {cur} đã là bản mới nhất.", "yt-dlp {cur} is already the latest."),
    "yu_getting": ("Đang tải yt-dlp {v}…", "Downloading yt-dlp {v}…"),
    "yu_done": ("Đã cập nhật yt-dlp lên {v}.\nHãy đóng và mở lại app để dùng bản mới.",
                "yt-dlp updated to {v}.\nClose and reopen the app to use it."),
    "yu_fail": ("Không cập nhật được yt-dlp: {e}\nKiểm tra mạng/VPN rồi thử lại.",
                "Could not update yt-dlp: {e}\nCheck your network/VPN and try again."),
    "yu_bad": ("File tải về bị hỏng hoặc không khớp mã kiểm tra.", "The downloaded file is damaged or does not match its checksum."),
    "vd_fail": ("Tải video thất bại: {e}\n(Nếu YouTube vừa thay đổi, thử cập nhật: {upd})",
                "Video download failed: {e}\n(If YouTube changed something, try updating: {upd})"),
}


def set_lang(lang):
    global LANG
    LANG = lang if lang in LANG_NAMES else "en"


def detect_lang():
    try:
        if os.name == "nt":
            import ctypes
            return "vi" if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x2A else "en"
        import locale
        loc = (os.environ.get("LANG") or os.environ.get("LC_ALL") or (locale.getlocale()[0] or "")).lower()
        return "vi" if loc.startswith("vi") else "en"
    except Exception:
        return "en"


def T(key, **kw):
    pair = STRINGS.get(key)
    if pair is None:
        return key
    s = pair[0] if LANG == "vi" else pair[1]
    return s.format(**kw) if kw else s


def _legacy_settings_path():
    base = os.environ.get("APPDATA") if os.name == "nt" else os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base or os.path.expanduser("~"), "ChatOverlay", "settings.json")


def _dir_writable(d):
    try:
        fd, tmp = tempfile.mkstemp(prefix=".w_", dir=d)
        os.close(fd)
        os.remove(tmp)
        return True
    except OSError:
        return False


def _settings_path():
    """Cài đặt nằm cạnh chat_overlay.py (không ghi vào ổ C). Chỉ khi thư mục đó không ghi được
    mới dùng %APPDATA%\\ChatOverlay (Windows) / ~/.config/ChatOverlay."""
    portable = os.path.join(SCRIPT_DIR, "settings.json")
    if os.path.isfile(portable) or _dir_writable(SCRIPT_DIR):
        return portable
    return _legacy_settings_path()


def _read_json(p):
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def load_settings():
    d = {}
    legacy = _legacy_settings_path()
    if legacy != _settings_path() and os.path.isfile(legacy):
        d.update(_read_json(legacy))          # cài đặt cũ (bản trước) – sẽ được chuyển sang file mới
    d.update(_read_json(_settings_path()))
    if not d.get("work_dir") and d.get("temp_dir"):
        d["work_dir"] = d["temp_dir"]          # bản trước chỉ có "thư mục tạm"
    return d


def save_settings(d):
    try:
        p = _settings_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        legacy = _legacy_settings_path()
        if legacy != p and os.path.isfile(legacy):
            os.remove(legacy)                  # đã chuyển xong -> xoá bản cũ trên ổ C
            try:
                os.rmdir(os.path.dirname(legacy))
            except OSError:
                pass
    except Exception:
        pass


def default_work_dir():
    if FROZEN and sys.platform == "darwin":
        # .app không nên bị ghi vào; dùng thư mục dữ liệu ứng dụng chuẩn của macOS.
        # Don't write inside the .app bundle; use the standard macOS app-data folder.
        return os.path.join(os.path.expanduser("~/Library/Application Support/ChatOverlay"), "work")
    return os.path.join(SCRIPT_DIR, "work")


def prepare_work_dir(work=""):
    """Tạo thư mục làm việc và chuyển MỌI file tạm của tiến trình (Python, ffmpeg, yt-dlp) vào đó."""
    work = os.path.abspath(os.path.expanduser(work.strip().strip('"') if work else default_work_dir()))
    tmp = os.path.join(work, "temp")
    try:
        os.makedirs(tmp, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix=".w_", dir=tmp)
        os.close(fd)
        os.remove(probe)
    except OSError as e:
        raise RuntimeError(T("no_work", p=work, e=e.strerror or e))
    tempfile.tempdir = tmp
    for var in ("TMP", "TEMP", "TMPDIR"):
        os.environ[var] = tmp                  # tiến trình con (ffmpeg, yt-dlp.exe) cũng dùng thư mục này
    return work


# ----------------------------------------------------------------------------- options
@dataclass
class Options:
    chat: str = ""
    output: str = ""
    video: str = ""
    fmt: str = "prores"         # prores | ffv1 | mov (Animation) | webm | green | burn
    style: str = "text"         # text | bubble | box
    position: str = "bottom-left"
    canvas: str = "box"         # box = chỉ đúng vùng khung chat (mặc định), full = cả khung hình video
    share_frames: bool = True   # ProRes/FFV1: nén mỗi khung KHÁC NHAU 1 lần, khung trùng dùng chung dữ liệu
    width: int = 1920
    height: int = 1080
    fps: float = 0.0            # 0 = theo video (không có video thì 30)
    max_messages: int = 10
    font_size: int = 22         # tính theo video 1080p, tự co giãn theo chiều cao video
    scale: float = 1.0
    box_width: int = 440
    box_height: int = 0         # 0 = tự tính để luôn chứa đủ max_messages tin
    # ===== VỊ TRÍ KHUNG CHAT / CHAT BOX POSITION =====
    # Khoảng cách (px, tính theo video 1080p, tự co giãn theo độ phân giải thật) từ khung chat đến mép hình.
    # Distance (px at 1080p, auto-scaled to the real resolution) from the chat box to the frame edges.
    margin_x: int = 40          # trái/phải — left/right
    margin_y: int = 40          # trên/dưới — top/bottom (giảm số này để khung chat xuống thấp hơn)
    min_gap: float = 0.10       # khoảng cách tối thiểu giữa 2 tin hiện ra (giây)
    anim: float = 0.12          # thời gian hiệu ứng trượt lên
    max_lag: float = 1.0        # nếu bị dồn lệch quá mức này thì hiện nhanh hơn
    hide_after: float = 0.0     # 0 = không tự ẩn tin cũ
    max_lines: int = 4
    offset: float = 0.0         # dời toàn bộ chat (giây), âm = sớm hơn
    start: float = 0.0
    end: float = 0.0            # 0 = đến hết
    avatars: bool = True
    download: bool = True
    font: str = ""
    font_bold: str = ""
    ffmpeg: str = ""
    cache_dir: str = ""
    work_dir: str = ""          # thư mục làm việc: temp/ (khung hình tạm), cache/ (avatar, emoji), yt-dlp-cache/
    temp_dir: str = ""          # ghi đè riêng chỗ chứa khung hình tạm (mặc định: <work_dir>/temp)
    encoder: str = "auto"       # bộ mã hoá cho burn/green: auto = ưu tiên GPU
    preview_at: float = -1.0    # >=0 -> chỉ xuất ảnh xem thử
    check_pair: bool = True     # cảnh báo khi file chat và video không cùng buổi live


def parse_time(s):
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    neg = s.startswith("-")
    v = 0.0
    for part in s.lstrip("-").split(":"):
        v = v * 60 + float(part)
    return -v if neg else v


def fmt_time(sec):
    sec = max(0.0, sec)
    h, m, s = int(sec // 3600), int(sec % 3600 // 60), sec % 60
    return f"{h}:{m:02d}:{s:04.1f}" if h else f"{m}:{s:04.1f}"


# ----------------------------------------------------------------------------- parsing
@dataclass
class Run:
    kind: str                 # text | emoji
    text: str = ""
    url: str = ""
    alt: str = ""
    custom: bool = False


@dataclass
class ChatMsg:
    kind: str = "text"        # text | paid | sticker | member
    id: str = ""
    t: float = 0.0
    seq: int = 0
    ts_usec: int = 0
    channel: str = ""
    author: str = ""
    avatar_url: str = ""
    role: str = ""            # owner | moderator | member | ""
    verified: bool = False
    badge_url: str = ""
    runs: list = field(default_factory=list)
    amount: str = ""
    sticker_url: str = ""
    header_bg: tuple = (208, 0, 0, 255)
    body_bg: tuple = (230, 33, 23, 255)
    header_fg: tuple = (255, 255, 255, 180)
    amount_fg: tuple = (255, 255, 255, 255)
    body_fg: tuple = (255, 255, 255, 255)
    dim: bool = False
    show: float = 0.0


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _argb(v, default):
    if v is None:
        return default
    v = int(v) & 0xFFFFFFFF
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255, (v >> 24) & 255)


def _upsize(url, px):
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    url = re.sub(r"=s\d+-", f"=s{px}-", url)
    url = re.sub(r"=w\d+-h\d+-", f"=w{px}-h{px}-", url)
    return url


def _text_of(obj):
    if not obj:
        return ""
    if "simpleText" in obj:
        return _nfc(obj["simpleText"])
    out = []
    for r in obj.get("runs", []):
        if "text" in r:
            out.append(r["text"])
        elif "emoji" in r:
            e = r["emoji"]
            out.append((e.get("shortcuts") or [""])[0] if e.get("isCustomEmoji") else e.get("emojiId", ""))
    return _nfc("".join(out))


def _runs(obj):
    if not obj:
        return []
    if "simpleText" in obj:
        return [Run("text", _nfc(obj["simpleText"]))]
    out = []
    for r in obj.get("runs", []):
        if "text" in r:
            out.append(Run("text", _nfc(r["text"])))
        elif "emoji" in r:
            e = r["emoji"]
            th = (e.get("image") or {}).get("thumbnails") or []
            custom = bool(e.get("isCustomEmoji"))
            out.append(Run("emoji",
                           url=_upsize(th[-1].get("url", "") if th else "", 96),
                           alt=(e.get("shortcuts") or [""])[0] if custom else e.get("emojiId", ""),
                           custom=custom))
    return out


def _author(v, m):
    m.author = _text_of(v.get("authorName"))
    th = (v.get("authorPhoto") or {}).get("thumbnails") or []
    m.avatar_url = _upsize(th[-1].get("url", ""), 128) if th else ""
    m.channel = v.get("authorExternalChannelId", "")
    for b in v.get("authorBadges") or []:
        br = b.get("liveChatAuthorBadgeRenderer") or {}
        icon = (br.get("icon") or {}).get("iconType", "")
        if icon == "OWNER":
            m.role = "owner"
        elif icon == "MODERATOR":
            if m.role != "owner":
                m.role = "moderator"
        elif icon in ("VERIFIED", "CHECK_CIRCLE_THICK", "CHECK"):
            m.verified = True
        elif br.get("customThumbnail"):
            th = br["customThumbnail"].get("thumbnails") or []
            if th:
                m.badge_url = _upsize(th[-1].get("url", ""), 64)
            if not m.role:
                m.role = "member"


def _parse_item(item):
    for key, v in item.items():
        if not isinstance(v, dict):
            continue
        if key == "liveChatTextMessageRenderer":
            m = ChatMsg("text")
            _author(v, m)
            m.runs = _runs(v.get("message"))
        elif key == "liveChatPaidMessageRenderer":
            m = ChatMsg("paid")
            _author(v, m)
            m.runs = _runs(v.get("message"))
            m.amount = _text_of(v.get("purchaseAmountText"))
            m.header_bg = _argb(v.get("headerBackgroundColor"), m.header_bg)
            m.body_bg = _argb(v.get("bodyBackgroundColor"), m.body_bg)
            m.header_fg = _argb(v.get("authorNameTextColor"), m.header_fg)
            m.amount_fg = _argb(v.get("headerTextColor"), m.amount_fg)
            m.body_fg = _argb(v.get("bodyTextColor"), m.body_fg)
        elif key == "liveChatPaidStickerRenderer":
            m = ChatMsg("sticker")
            _author(v, m)
            m.amount = _text_of(v.get("purchaseAmountText"))
            th = (v.get("sticker") or {}).get("thumbnails") or []
            m.sticker_url = _upsize(th[-1].get("url", ""), 144) if th else ""
            bg = _argb(v.get("backgroundColor") or v.get("moneyChipBackgroundColor"), (0, 184, 212, 255))
            m.header_bg = m.body_bg = bg
            m.header_fg = _argb(v.get("authorNameTextColor"), (255, 255, 255, 180))
            m.amount_fg = _argb(v.get("moneyChipTextColor"), (255, 255, 255, 255))
        elif key == "liveChatMembershipItemRenderer":
            m = ChatMsg("member")
            _author(v, m)
            m.runs = _runs(v.get("message"))
            m.amount = _text_of(v.get("headerPrimaryText")) or _text_of(v.get("headerSubtext")) or "Thành viên mới"
            m.header_bg, m.body_bg = (15, 157, 88, 255), (11, 128, 67, 255)
            m.header_fg = (255, 255, 255, 190)
        elif key == "liveChatSponsorshipsGiftPurchaseAnnouncementRenderer":
            h = (v.get("header") or {}).get("liveChatSponsorshipsHeaderRenderer") or {}
            m = ChatMsg("member")
            _author(h, m)
            m.channel = m.channel or v.get("authorExternalChannelId", "")
            m.amount = _text_of(h.get("primaryText")) or "Tặng thành viên"
            m.header_bg, m.body_bg = (15, 157, 88, 255), (11, 128, 67, 255)
            m.header_fg = (255, 255, 255, 190)
        elif key == "liveChatSponsorshipsGiftRedemptionAnnouncementRenderer":
            m = ChatMsg("text")
            _author(v, m)
            m.runs = _runs(v.get("message"))
            m.dim = True
        else:
            continue
        m.id = v.get("id", "")
        m.ts_usec = int(v.get("timestampUsec") or 0)
        return m
    return None


def load_chat(path, log=print):
    with open(path, "r", encoding="utf-8-sig") as f:
        content = f.read()
    objs = []
    if content.lstrip().startswith("["):
        try:
            objs = json.loads(content)
        except json.JSONDecodeError:
            objs = []
    if not objs:
        bad = 0
        for ln in content.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                objs.append(json.loads(ln))
            except json.JSONDecodeError:
                bad += 1
        if bad:
            log(T("skip_bad", n=bad))
    msgs, deleted, banned, seq = [], set(), set(), 0
    for o in objs:
        if not isinstance(o, dict):
            continue
        r = o.get("replayChatItemAction")
        if r:
            actions, off = r.get("actions") or [], r.get("videoOffsetTimeMsec")
        else:
            actions, off = o.get("actions") or [o], o.get("videoOffsetTimeMsec")
        for a in actions:
            if not isinstance(a, dict):
                continue
            if "addChatItemAction" in a:
                m = _parse_item((a["addChatItemAction"] or {}).get("item") or {})
                if m:
                    m.t = int(off) / 1000.0 if off is not None else None
                    m.seq = seq
                    seq += 1
                    msgs.append(m)
            elif "markChatItemAsDeletedAction" in a:
                deleted.add(a["markChatItemAsDeletedAction"].get("targetItemId"))
            elif "removeChatItemAction" in a:
                deleted.add(a["removeChatItemAction"].get("targetItemId"))
            elif "markChatItemsByAuthorAsDeletedAction" in a:
                banned.add(a["markChatItemsByAuthorAsDeletedAction"].get("externalChannelId"))
            elif "removeChatItemByAuthorAction" in a:
                banned.add(a["removeChatItemByAuthorAction"].get("externalChannelId"))
    missing = [m for m in msgs if m.t is None]
    if missing:
        ts = [m.ts_usec for m in msgs if m.ts_usec]
        t0 = min(ts) if ts else 0
        for m in missing:
            m.t = (m.ts_usec - t0) / 1e6 if m.ts_usec else 0.0
        log(T("no_offset", n=len(missing)))
    n0 = len(msgs)
    deleted.discard(None)
    banned.discard(None)
    msgs = [m for m in msgs if m.id not in deleted and not (m.channel and m.channel in banned)]
    msgs.sort(key=lambda m: (m.t, m.seq))
    return msgs, n0 - len(msgs)


def schedule(msgs, o):
    """Xếp hàng: mỗi tin hiện ra sau tin trước ít nhất min_gap giây -> không bao giờ hiện cùng lúc.
    Đợt tin dồn được dàn đều quanh mốc thật (vài tin hiện sớm, vài tin muộn) thay vì chỉ đẩy lùi về sau:
    trung bình của lượt xuôi (chỉ trễ) và lượt ngược (chỉ sớm) là cách xếp có độ lệch lớn nhất nhỏ nhất,
    và vẫn giữ khoảng cách ≥ khoảng cách nhỏ nhất của hai lượt.
    Bursts are spread around the true time instead of only pushed later: averaging a forward (late-only)
    and a backward (early-only) pass minimises the worst deviation while keeping the minimum gap.
    Trả về (trễ lớn nhất, sớm lớn nhất) / Returns (max late, max early)."""
    gap = max(o.min_gap, 0.05)
    fast_gap = max(min(gap, o.anim) / 2.5, 0.06)
    base = [m.t + o.offset for m in msgs]
    n = len(msgs)
    fwd, prev = [0.0] * n, -1e18
    for i in range(n):
        g = gap if (prev + gap - base[i]) <= o.max_lag else fast_gap
        prev = fwd[i] = max(base[i], prev + g)
    bwd, nxt = [0.0] * n, 1e18
    for i in range(n - 1, -1, -1):
        g = gap if (base[i] - (nxt - gap)) <= o.max_lag else fast_gap
        nxt = bwd[i] = min(base[i], nxt - g)
    late = early = 0.0
    for i, m in enumerate(msgs):
        m.show = (fwd[i] + bwd[i]) / 2
        late = max(late, m.show - base[i])
        early = max(early, base[i] - m.show)
    return late, early


# ----------------------------------------------------------------------------- chat ↔ video pairing check
def _name_date(path):
    """Ngày ghi trong tên file: 230917, 2309111 (ngày + số phần), 20230917, 2023-09-17, 17⧸09⧸2023…
    Date written in a file name (yt-dlp turns "/" into "⧸"). Returns datetime.date or None."""
    import datetime
    name = os.path.basename(path)
    name = re.sub(r"(\.live_chat)?\.[^.]+$", "", name)
    pats = [(r"(?<!\d)(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})(?!\d)", "ymd"),
            (r"(?<!\d)(\d{1,2})[⧸/._-](\d{1,2})[⧸/._-](20\d{2})(?!\d)", "dmy"),
            (r"^(\d{2})(\d{2})(\d{2})(?:\d{1,2})?(?!\d)", "ymd2")]
    for pat, kind in pats:
        m = re.search(pat, name)
        if not m:
            continue
        a, b, c = (int(x) for x in m.groups())
        y, mo, d = (a, b, c) if kind == "ymd" else (c, b, a) if kind == "dmy" else (2000 + a, b, c)
        try:
            return datetime.date(y, mo, d)
        except ValueError:
            continue
    return None


def _name_id(path):
    m = re.search(r"\[([A-Za-z0-9_-]{11})\]", os.path.basename(path))
    return m.group(1) if m else None


def check_pair(chat_path, video_path, msgs, vdur):
    """Tìm dấu hiệu file chat và video thuộc hai buổi live khác nhau (đặt nhầm tên, chọn nhầm file).
    Find signs that the chat and the video come from different streams. Returns a list of reasons."""
    import datetime
    import statistics
    why = []
    last = msgs[-1].t if msgs else 0.0
    if vdur > 0 and last > vdur + 120:          # chat còn tin sau khi video đã hết vài phút
        why.append(T("mm_len", c=fmt_time(last), v=fmt_time(vdur)))
    elif vdur > 1800 and last < vdur * 0.5:     # video dài gấp đôi phần có chat
        why.append(T("mm_short", c=fmt_time(last), v=fmt_time(vdur), p=int(last / vdur * 100)))
    # Giờ bắt đầu buổi live = giờ gửi thật của tin trừ mốc của tin trong video (trung vị cho chắc).
    # Không biết múi giờ người phát -> chấp nhận mọi ngày mà giờ đó rơi vào ở UTC−12…UTC+14.
    # Stream start = real send time minus the message's offset (median). The streamer's time zone is unknown,
    # so accept every calendar day that instant falls on somewhere between UTC−12 and UTC+14.
    starts = [m.ts_usec / 1e6 - m.t for m in msgs if m.ts_usec]
    days = set()
    if starts:
        t0 = datetime.datetime.fromtimestamp(statistics.median(starts), datetime.timezone.utc)
        days = {(t0 + datetime.timedelta(hours=h)).date() for h in range(-12, 15)}
    show = lambda d: d.strftime("%d/%m/%Y")
    chat_days = t0.astimezone().strftime("%H:%M %d/%m/%Y") if starts else ""
    v_day, c_day = _name_date(video_path), _name_date(chat_path)
    if days and v_day and v_day not in days:
        why.append(T("mm_date_v", c=chat_days, n=show(v_day)))
    if days and c_day and c_day not in days:
        why.append(T("mm_date_c", c=chat_days, n=show(c_day)))
    if v_day and c_day and v_day != c_day:      # buổi liền nhau lọt qua sai số múi giờ / catches adjacent days
        why.append(T("mm_name", a=show(c_day), b=show(v_day)))
    a, b = _name_id(chat_path), _name_id(video_path)
    if a and b and a != b:
        why.append(T("mm_id", a=a, b=b))
    return why


# ----------------------------------------------------------------------------- fonts & assets
REGULAR_FONTS = [
    "Roboto-Regular.ttf", "NotoSans-Regular.ttf", "BeVietnamPro-Regular.ttf",
    os.path.join(WIN_FONTS, "segoeui.ttf"), os.path.join(WIN_FONTS, "arial.ttf"),
    "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Regular.ttf",
    "/usr/share/fonts/truetype/roboto/hinted/Roboto-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf",
]
BOLD_FONTS = [
    "Roboto-Medium.ttf", "Roboto-Bold.ttf", "NotoSans-SemiBold.ttf", "NotoSans-Bold.ttf", "BeVietnamPro-SemiBold.ttf",
    os.path.join(WIN_FONTS, "seguisb.ttf"), os.path.join(WIN_FONTS, "segoeuib.ttf"), os.path.join(WIN_FONTS, "arialbd.ttf"),
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Medium.ttf",
    "/usr/share/fonts/truetype/roboto/hinted/Roboto-Medium.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", "/usr/share/fonts/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]
EMOJI_FONTS = [
    os.path.join(WIN_FONTS, "seguiemj.ttf"), "/System/Library/Fonts/Apple Color Emoji.ttc",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", "/usr/share/fonts/noto/NotoColorEmoji.ttf",
]


def _find_font(cands):
    for c in cands:
        p = c if os.path.isabs(c) else os.path.join(SCRIPT_DIR, "fonts", c)
        if os.path.isfile(p):
            return p
    return None


class Fonts:
    def __init__(self, regular="", bold="", log=print):
        self.reg = regular if regular and os.path.isfile(regular) else _find_font(REGULAR_FONTS)
        self.bold = bold if bold and os.path.isfile(bold) else (_find_font(BOLD_FONTS) or self.reg)
        if not self.reg:
            log(T("no_font"))
        else:
            log(f"  Font: {os.path.basename(self.reg)} / {os.path.basename(self.bold)}")
        self._cache = {}

    def get(self, size, bold=False):
        k = (size, bold)
        if k not in self._cache:
            p = self.bold if bold else self.reg
            try:
                f = ImageFont.truetype(p, size) if p else ImageFont.load_default(size)
            except Exception:
                f = ImageFont.load_default()
            self._cache[k] = f
        return self._cache[k]


class EmojiFont:
    """Dự phòng khi không tải được ảnh emoji: vẽ bằng font emoji màu của hệ thống."""

    def __init__(self):
        self.font, self.sz = None, 0
        path = _find_font(EMOJI_FONTS)
        if path:
            for sz in (109, 96, 136, 160, 64, 48):
                try:
                    self.font, self.sz = ImageFont.truetype(path, sz), sz
                    break
                except Exception:
                    pass
        self.cache = {}

    def render(self, ch, px):
        if not self.font or not ch:
            return None
        k = (ch, px)
        if k not in self.cache:
            img = None
            try:
                s = self.sz
                im = Image.new("RGBA", (s * 2 * len(ch) + s, s * 2), (0, 0, 0, 0))
                ImageDraw.Draw(im).text((s // 4, s // 4), ch, font=self.font, embedded_color=True)
                bb = im.getbbox()
                if bb:
                    im = im.crop(bb)
                    r = px / max(im.size)
                    img = im.resize((max(1, round(im.width * r)), max(1, round(im.height * r))), RESAMPLE)
            except Exception:
                img = None
            self.cache[k] = img
        return self.cache[k]


class Assets:
    """Tải & cache avatar, emoji, badge (lưu vào thư mục cache để lần sau không tải lại)."""

    def __init__(self, cache_dir, enabled=True, log=print):
        self.dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.enabled = enabled
        self.log = log
        self.mem = {}

    def _path(self, url):
        return os.path.join(self.dir, hashlib.sha1(url.encode("utf-8")).hexdigest() + ".img")

    def _download(self, url, timeout=15):
        p = self._path(url)
        if os.path.isfile(p) and os.path.getsize(p) > 0:
            return True
        if not self.enabled:
            return False
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            Image.open(io.BytesIO(data)).verify()
            with open(p + ".part", "wb") as f:
                f.write(data)
            os.replace(p + ".part", p)
            return True
        except Exception:
            return False

    def prefetch(self, urls, progress=None, cancel=None):
        urls = [u for u in dict.fromkeys(urls) if u]
        todo = [u for u in urls if not os.path.isfile(self._path(u))]
        if todo and self.enabled:
            # thử 1 link trước: nếu không có mạng thì bỏ qua cả loạt cho nhanh
            if not self._download(todo[0], timeout=8):
                self.log(T("no_net"))
                self.enabled = False
        ok = 0
        if self.enabled and todo:
            with ThreadPoolExecutor(max_workers=16) as ex:
                for i, res in enumerate(ex.map(self._download, todo)):
                    ok += bool(res)
                    if progress:
                        progress("download", (i + 1) / len(todo))
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
        return len(urls) - len(todo) + ok, len(urls)

    def get(self, url, size, square=False):
        k = (url, size, square)
        if k in self.mem:
            return self.mem[k]
        img = None
        p = self._path(url) if url else ""
        if p and os.path.isfile(p):
            try:
                im = Image.open(p)
                im.seek(0)
                im = im.convert("RGBA")
                if square:
                    img = im.resize((size, size), RESAMPLE)
                else:
                    r = size / max(im.size)
                    img = im.resize((max(1, round(im.width * r)), max(1, round(im.height * r))), RESAMPLE)
            except Exception:
                img = None
        self.mem[k] = img
        return img


# ----------------------------------------------------------------------------- rendering
TEXT_COLOR = (255, 255, 255, 255)
DIM_COLOR = (185, 185, 185, 255)
NAME_COLORS = {"": (205, 205, 205, 255), "member": (80, 214, 110, 255),
               "moderator": (125, 165, 255, 255), "owner": (25, 25, 25, 255)}
OWNER_PILL = (255, 214, 0, 255)
BUBBLE_BG = (0, 0, 0, 150)
PANEL_BG = (10, 10, 10, 150)


class Geometry:
    def __init__(self, o, canvas_h):
        S = canvas_h / 1080.0 * o.scale
        px = lambda v: max(1, int(round(v * S)))
        self.S = S
        self.fs = px(o.font_size)
        self.fs_small = max(8, int(round(self.fs * 0.88)))
        self.line_h = int(round(self.fs * 1.42))
        self.av = int(round(self.fs * 1.5))
        self.gap = px(10)
        self.emoji = int(round(self.fs * 1.3))
        self.spacing = px(8 if o.style == "bubble" else 6)
        self.pad_x, self.pad_y = px(12), px(6)
        self.radius = px(17)
        self.card_r = px(8)
        self.stroke = max(1, int(round(self.fs * 0.1))) if o.style == "text" else 0
        self.panel_pad = px(12) if o.style == "box" else 0
        self.box_w = (px(o.box_width) // 2) * 2
        self.inner_w = self.box_w - 2 * self.panel_pad
        self.margin_x = int(round(o.margin_x * S))
        self.margin_y = int(round(o.margin_y * S))
        self.fade_h = px(26)


class Tok:
    __slots__ = ("kind", "text", "font", "color", "w", "img", "pad", "pill")

    def __init__(self, kind, text="", font=None, color=None, w=0.0, img=None, pad=0, pill=None):
        self.kind, self.text, self.font, self.color = kind, text, font, color
        self.w, self.img, self.pad, self.pill = w, img, pad, pill


def _blend(fg, bg):
    """Trộn màu chữ bán trong suốt lên nền đặc (ImageDraw trên RGBA không tự trộn)."""
    a = fg[3] / 255.0
    return tuple(int(round(fg[i] * a + bg[i] * (1 - a))) for i in range(3)) + (255,)


class MsgRenderer:
    def __init__(self, o, g, fonts, assets, emoji_font):
        self.o, self.g, self.assets, self.ef = o, g, assets, emoji_font
        self.f = fonts.get(g.fs)
        self.fb = fonts.get(g.fs, True)
        self.f_small = fonts.get(g.fs_small)
        bb = self.f.getbbox("Hgy", anchor="ls")
        self.base_off = int(round(g.line_h / 2 - (bb[1] + bb[3]) / 2))
        self.emoji_pad = max(1, int(round(g.fs * 0.08)))
        self.pill_px = max(2, int(round(g.fs * 0.3)))
        self._av_cache, self._mask_cache, self._icons = {}, {}, {}

    # ---- small graphics
    def _circle_mask(self, d):
        if d not in self._mask_cache:
            big = Image.new("L", (d * 4, d * 4), 0)
            ImageDraw.Draw(big).ellipse([0, 0, d * 4 - 1, d * 4 - 1], fill=255)
            self._mask_cache[d] = big.resize((d, d), RESAMPLE)
        return self._mask_cache[d]

    def _avatar(self, m):
        d = self.g.av
        key = m.avatar_url or ("?", m.author)
        if key in self._av_cache:
            return self._av_cache[key]
        src = self.assets.get(m.avatar_url, d, square=True) if m.avatar_url else None
        if src is None:
            h = int(hashlib.md5(m.author.encode("utf-8")).hexdigest()[:6], 16) / 0xFFFFFF
            r, gg, b = colorsys.hsv_to_rgb(h, 0.55, 0.78)
            src = Image.new("RGBA", (d, d), (int(r * 255), int(gg * 255), int(b * 255), 255))
            letter = next((c for c in m.author.lstrip("@") if c.isalnum()), "?").upper()
            fb = self.f if self.f is self.fb else self.fb
            ImageDraw.Draw(src).text((d / 2, d / 2), letter, font=fb, fill=(255, 255, 255, 255), anchor="mm")
        out = src.copy()
        out.putalpha(ImageChops.multiply(src.getchannel("A"), self._circle_mask(d)))
        self._av_cache[key] = out
        return out

    def _icon(self, kind, color):
        k = (kind, color)
        if k in self._icons:
            return self._icons[k]
        sz = max(8, int(round(self.g.fs * 0.85)))
        S = sz * 4
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if kind == "verified":
            d.line([(0.12 * S, 0.52 * S), (0.4 * S, 0.8 * S), (0.9 * S, 0.22 * S)], fill=color, width=int(0.16 * S), joint="curve")
        else:  # wrench (moderator)
            w = int(0.2 * S)
            d.line([(0.18 * S, 0.82 * S), (0.6 * S, 0.4 * S)], fill=color, width=w)
            d.ellipse([0.18 * S - w / 2, 0.82 * S - w / 2, 0.18 * S + w / 2, 0.82 * S + w / 2], fill=color)
            d.ellipse([0.42 * S, 0.1 * S, 0.92 * S, 0.6 * S], fill=color)
            d.ellipse([0.66 * S, -0.06 * S, 1.04 * S, 0.32 * S], fill=(0, 0, 0, 0))
        im = im.resize((sz, sz), RESAMPLE)
        self._icons[k] = im
        return im

    def _placeholder_emoji(self):
        """Mặt cười vàng thay cho emoji riêng của kênh khi không tải được ảnh."""
        if "ph" not in self._icons:
            sz = self.g.emoji
            S = sz * 4
            im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.ellipse([S * 0.06, S * 0.06, S * 0.94, S * 0.94], fill=(255, 202, 40, 255))
            for ex in (0.34, 0.66):
                d.ellipse([S * (ex - 0.07), S * 0.3, S * (ex + 0.07), S * 0.48], fill=(60, 40, 10, 255))
            d.arc([S * 0.26, S * 0.3, S * 0.74, S * 0.76], 25, 155, fill=(60, 40, 10, 255), width=int(S * 0.07))
            self._icons["ph"] = im.resize((sz, sz), RESAMPLE)
        return self._icons["ph"]

    # ---- text layout
    def _run_tokens(self, runs, font, color):
        toks = []
        for r in runs:
            if r.kind == "text":
                for piece in re.split(r"(\s+)", r.text):
                    if not piece:
                        continue
                    if piece.isspace():
                        toks.append(Tok("space", " ", font, color, font.getlength(" ")))
                    else:
                        toks.append(Tok("word", piece, font, color, font.getlength(piece)))
            else:
                img = self.assets.get(r.url, self.g.emoji) if r.url else None
                if img is None and not r.custom:
                    img = self.ef.render(r.alt, self.g.emoji)
                if img is None and r.custom:
                    img = self._placeholder_emoji()
                if img is not None:
                    toks.append(Tok("img", img=img, w=img.width + 2 * self.emoji_pad, pad=self.emoji_pad))
                elif r.alt:
                    toks.append(Tok("word", r.alt, font, color, font.getlength(r.alt)))
        return toks

    def _split_word(self, tk, maxw, first_avail):
        chunks, s = [], ""
        avail = first_avail if first_avail > maxw * 0.3 else maxw
        for ch in tk.text:
            if s and tk.font.getlength(s + ch) > avail:
                chunks.append(s)
                s, avail = ch, maxw
            else:
                s += ch
        if s:
            chunks.append(s)
        return [Tok("word", c, tk.font, tk.color, tk.font.getlength(c)) for c in chunks]

    def _wrap(self, toks, maxw, max_lines, ell_color):
        lines, cur, x = [], [], 0.0

        def flush():
            nonlocal cur, x
            while cur and cur[-1][0].kind in ("space", "gap"):
                cur.pop()
            lines.append(cur)
            cur, x = [], 0.0

        for tk in toks:
            if tk.kind in ("space", "gap"):
                if cur:
                    cur.append((tk, x))
                    x += tk.w
                continue
            if tk.kind == "word" and tk.w > maxw:
                for ch in self._split_word(tk, maxw, maxw - x):
                    if cur and x + ch.w > maxw:
                        flush()
                    cur.append((ch, x))
                    x += ch.w
                continue
            if cur and x + tk.w > maxw:
                flush()
            cur.append((tk, x))
            x += tk.w
        if cur or not lines:
            flush()
        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
            last = lines[-1]
            ell = Tok("word", "…", self.f, ell_color, self.f.getlength("…"))
            while last and (last[-1][0].kind in ("space", "gap") or last[-1][1] + last[-1][0].w + ell.w > maxw):
                last.pop()
            last.append((ell, last[-1][1] + last[-1][0].w if last else 0.0))
        return lines

    @staticmethod
    def _line_w(line):
        return max((x + tk.w for tk, x in line if tk.kind not in ("space", "gap")), default=0.0)

    def _draw_line(self, img, d, line, ox, oy, stroke):
        g = self.g
        base = oy + self.base_off
        sf = (0, 0, 0, 255)
        i = 0
        while i < len(line):
            tk, x = line[i]
            if tk.kind == "gap" or tk.kind == "space":
                i += 1
                continue
            if tk.kind == "img":
                im = tk.img
                img.alpha_composite(im, (int(round(ox + x + tk.pad)), int(oy + (g.line_h - im.height) // 2)))
                i += 1
                continue
            if tk.kind == "name":
                if tk.pill:
                    ph = int(round(g.fs * 1.25))
                    y0 = oy + (g.line_h - ph) // 2
                    d.rounded_rectangle([ox + x, y0, ox + x + tk.w, y0 + ph], radius=ph // 2, fill=tk.pill)
                    d.text((ox + x + self.pill_px, base), tk.text, font=tk.font, fill=tk.color, anchor="ls")
                else:
                    d.text((ox + x, base), tk.text, font=tk.font, fill=tk.color, anchor="ls",
                           stroke_width=stroke, stroke_fill=sf)
                i += 1
                continue
            s, j = tk.text, i + 1
            while j < len(line) and line[j][0].kind in ("word", "space") and line[j][0].font is tk.font \
                    and line[j][0].color == tk.color:
                s += line[j][0].text
                j += 1
            d.text((ox + x, base), s.rstrip(), font=tk.font, fill=tk.color, anchor="ls",
                   stroke_width=stroke, stroke_fill=sf)
            i = j

    def _fit(self, text, font, limit):
        if font.getlength(text) <= limit:
            return text
        while text and font.getlength(text + "…") > limit:
            text = text[:-1]
        return text + "…"

    # ---- message kinds
    def render(self, m):
        if m.kind in ("paid", "sticker", "member"):
            return self._render_card(m)
        return self._render_text(m)

    def _render_text(self, m):
        g, o = self.g, self.o
        bubble = o.style == "bubble"
        px_ = g.pad_x if bubble else g.stroke + 1
        py_ = g.pad_y if bubble else g.stroke + 1
        av = g.av if o.avatars else 0
        tx = av + g.gap if av else 0
        maxw = g.inner_w - 2 * px_ - tx

        toks = []
        pill = OWNER_PILL if m.role == "owner" else None
        name = self._fit(m.author, self.fb, maxw * 0.75 - (2 * self.pill_px if pill else 0))
        nt = Tok("name", name, self.fb, NAME_COLORS.get(m.role, NAME_COLORS[""]), self.fb.getlength(name), pill=pill)
        if pill:
            nt.w += 2 * self.pill_px
        toks.append(nt)
        icons = []
        if m.verified:
            icons.append(self._icon("verified", (200, 200, 200, 255)))
        if m.role == "moderator":
            icons.append(self._icon("wrench", NAME_COLORS["moderator"]))
        if m.badge_url:
            bimg = self.assets.get(m.badge_url, max(8, int(round(g.fs * 0.85))))
            if bimg is not None:
                icons.append(bimg)
        for ic in icons:
            p = max(1, int(round(g.fs * 0.15)))
            toks.append(Tok("img", img=ic, w=ic.width + p, pad=p))
        toks.append(Tok("gap", w=self.f.getlength(" ") * 1.5))
        col = DIM_COLOR if m.dim else TEXT_COLOR
        toks += self._run_tokens(m.runs, self.f, col)

        lines = self._wrap(toks, maxw, o.max_lines, col)
        lw = max(self._line_w(l) for l in lines)
        lh = g.line_h
        ty = max(0, (av - lh) // 2) if av else 0
        ay = ty + (lh - av) // 2
        content_h = max(ay + av, ty + len(lines) * lh)
        w = int(min(g.inner_w, 2 * px_ + tx + lw + 2)) if bubble else g.inner_w
        h = content_h + 2 * py_
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if bubble:
            d.rounded_rectangle([0, 0, w - 1, h - 1], radius=min(g.radius, h // 2), fill=BUBBLE_BG)
        if av:
            img.alpha_composite(self._avatar(m), (px_, py_ + ay))
        for k, line in enumerate(lines):
            self._draw_line(img, d, line, px_ + tx, py_ + ty + k * lh, g.stroke)
        return img

    def _render_card(self, m):
        g, o = self.g, self.o
        w = g.inner_w
        pad = g.pad_x
        av = g.av if o.avatars else 0
        hx = pad + (av + g.gap if av else 0)
        l1 = int(round(g.fs_small * 1.3))
        l2 = int(round(g.fs * 1.3))
        header_h = 2 * pad + max(av, l1 + l2)
        body_fg = _blend(m.body_fg, m.body_bg)
        lines, body_h, sticker = [], 0, None
        if m.kind == "sticker":
            sticker = self.assets.get(m.sticker_url, int(round(g.fs * 3))) if m.sticker_url else None
            if sticker is not None:
                body_h = sticker.height + 2 * pad
        elif m.runs:
            toks = self._run_tokens(m.runs, self.f, body_fg)
            lines = self._wrap(toks, w - 2 * pad, o.max_lines, body_fg)
            body_h = len(lines) * g.line_h + 2 * g.pad_y + pad // 2
        h = header_h + body_h
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = g.card_r
        if body_h:
            d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=m.body_bg[:3] + (255,))
            d.rounded_rectangle([0, 0, w - 1, header_h - 1], radius=r, fill=m.header_bg[:3] + (255,))
            d.rectangle([0, header_h - r, w - 1, header_h - 1], fill=m.header_bg[:3] + (255,))
        else:
            d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=m.header_bg[:3] + (255,))
        if av:
            img.alpha_composite(self._avatar(m), (pad, (header_h - av) // 2))
        ty = (header_h - (l1 + l2)) // 2
        limit = w - hx - pad
        d.text((hx, ty + int(l1 * 0.8)), self._fit(m.author, self.f_small, limit), font=self.f_small,
               fill=_blend(m.header_fg, m.header_bg), anchor="ls")
        d.text((hx, ty + l1 + int(l2 * 0.78)), self._fit(m.amount, self.fb, limit), font=self.fb,
               fill=_blend(m.amount_fg, m.header_bg), anchor="ls")
        if sticker is not None:
            img.alpha_composite(sticker, (pad, header_h + pad))
        for k, line in enumerate(lines):
            self._draw_line(img, d, line, pad, header_h + g.pad_y + pad // 4 + k * g.line_h, 0)
        return img


# ----------------------------------------------------------------------------- timeline & compositing
class Timeline:
    def __init__(self, shows, heights, anim, spacing, maxv, hide_after):
        self.shows, self.heights, self.spacing, self.maxv, self.hide = shows, heights, spacing, maxv, hide_after
        n = len(shows)
        # hiệu ứng của tin k không bao giờ chồng lên tin k+1
        self.anims = [min(anim, shows[k + 1] - shows[k]) if k + 1 < n else anim for k in range(n)]

    def _age_alpha(self, i, t):
        if self.hide <= 0:
            return 1.0
        rem = self.shows[i] + self.hide - t
        return 0.0 if rem <= 0 else min(1.0, rem / 0.4)

    def key(self, t):
        k = bisect.bisect_right(self.shows, t) - 1
        if k < 0:
            return (0, ())
        ad = self.anims[k]
        p = 1.0 if ad <= 0 else min(1.0, (t - self.shows[k]) / ad)
        e = 1 - (1 - p) ** 3
        items = []
        if p < 1 and k - self.maxv >= 0:          # tin cũ nhất đang trượt ra ngoài
            a = self._age_alpha(k - self.maxv, t) * (1 - e)
            if a > 0.004:
                items.append((k - self.maxv, a))
        for i in range(max(0, k - self.maxv + 1), k + 1):
            a = self._age_alpha(i, t) * (e if i == k else 1.0)
            if a > 0.004:
                items.append((i, a))
        shift = int(round((self.heights[k] + self.spacing) * (1 - e))) if p < 1 else 0
        return (shift, tuple((i, int(round(a * 255))) for i, a in items))


def _paste(dst, im, x, y):
    if y < 0:
        if -y >= im.height:
            return
        im = im.crop((0, -y, im.width, im.height))
        y = 0
    if y >= dst.height:
        return
    if y + im.height > dst.height:
        im = im.crop((0, 0, im.width, dst.height - y))
    dst.alpha_composite(im, (int(x), int(y)))


def _fade(im, a):
    out = im.copy()
    out.putalpha(im.getchannel("A").point(lambda v, a=a: v * a // 255))
    return out


class Compositor:
    def __init__(self, o, g, renderer, msgs, box_h):
        self.g, self.r, self.msgs = g, renderer, msgs
        self.W, self.H = g.box_w, box_h
        self.cache = OrderedDict()
        top = g.panel_pad
        mask = Image.new("L", (1, self.H), 255)
        for yy in range(self.H):
            if yy < top:
                mask.putpixel((0, yy), 0)
            elif yy < top + g.fade_h:
                mask.putpixel((0, yy), int(255 * (yy - top) / g.fade_h))
        self.mask = mask.resize((self.W, self.H))
        self.panel = None
        if o.style == "box":
            self.panel = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
            ImageDraw.Draw(self.panel).rounded_rectangle([0, 0, self.W - 1, self.H - 1], radius=g.radius, fill=PANEL_BG)

    def msg_img(self, i):
        im = self.cache.get(i)
        if im is None:
            im = self.r.render(self.msgs[i])
            self.cache[i] = im
            if len(self.cache) > 64:
                self.cache.popitem(last=False)
        else:
            self.cache.move_to_end(i)
        return im

    def compose(self, key):
        shift, items = key
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        y = self.H - self.g.panel_pad + shift
        for i, a in reversed(items):
            im = self.msg_img(i)
            y -= im.height
            if y + im.height <= 0:
                break
            _paste(layer, im if a >= 255 else _fade(im, a), self.g.panel_pad, y)
            y -= self.g.spacing
        layer.putalpha(ImageChops.multiply(layer.getchannel("A"), self.mask))
        if self.panel is not None:
            out = self.panel.copy()
            out.alpha_composite(layer)
            return out
        return layer


# ----------------------------------------------------------------------------- ffmpeg helpers
def find_tool(name, explicit=""):
    exe = name + (".exe" if os.name == "nt" else "")
    if explicit:
        p = os.path.join(explicit, exe) if os.path.isdir(explicit) else (
            os.path.join(os.path.dirname(explicit), exe) if name != "ffmpeg" else explicit)
        if os.path.isfile(p):
            return p
    for p in (os.path.join(SCRIPT_DIR, exe), os.path.join(SCRIPT_DIR, "ffmpeg", "bin", exe)):
        if os.path.isfile(p):
            return p
    found = shutil.which(name)
    if found:
        return found
    if sys.platform == "darwin":
        # App launched từ Finder không kế thừa PATH của shell (thiếu Homebrew).
        # An app launched from Finder doesn't inherit the shell's PATH (missing Homebrew).
        for d in ("/opt/homebrew/bin", "/usr/local/bin"):
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    return None


def _popen_kw():
    return {"creationflags": 0x08000000} if os.name == "nt" else {}


def probe_video(ffprobe, path):
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
           "stream=width,height,avg_frame_rate,r_frame_rate,duration,nb_frames:stream_tags=DURATION:format=duration",
           "-of", "json", path]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_popen_kw())
    info = json.loads(res.stdout.decode("utf-8", "replace") or "{}")
    st = (info.get("streams") or [{}])[0]

    def rate(s):
        try:
            a, b = s.split("/")
            return float(a) / float(b) if float(b) else 0.0
        except Exception:
            return 0.0
    fps = rate(st.get("avg_frame_rate", "")) or rate(st.get("r_frame_rate", ""))
    # Lấy độ dài của luồng HÌNH, không phải của cả file: tiếng thường dài hơn hình vài khung,
    # khiến file chat dài hơn clip video trong DaVinci. MKV/WebM ghi độ dài luồng trong thẻ DURATION.
    # Use the VIDEO stream's length, not the container's: audio often runs a few frames longer, which made the
    # chat clip longer than the video clip in DaVinci. MKV/WebM keep the stream length in a DURATION tag.
    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
    dur = num(st.get("duration"))
    if dur <= 0:                                   # MKV/WebM: "01:02:03.456000000"
        tag = str((st.get("tags") or {}).get("DURATION") or "")
        try:
            h, m, sec = tag.split(":")
            dur = int(h) * 3600 + int(m) * 60 + float(sec)
        except ValueError:
            pass
    if dur <= 0 and fps > 0:
        dur = num(st.get("nb_frames")) / fps
    if dur <= 0:
        dur = num((info.get("format") or {}).get("duration"))
    if not st.get("width"):
        raise RuntimeError(T("ffprobe_fail") + res.stderr.decode("utf-8", "replace")[-500:])
    return int(st["width"]), int(st["height"]), fps, dur


def run_ffmpeg(cmd, total, progress, cancel, log):
    log("  ffmpeg: " + " ".join(c if " " not in c else f'"{c}"' for c in cmd[1:])[:400])
    errf = tempfile.TemporaryFile()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf, stdin=subprocess.DEVNULL, **_popen_kw())
    try:
        for raw in p.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    sec = int(line.split("=", 1)[1]) / 1e6
                    if progress and total > 0:
                        progress("encode", min(1.0, sec / total))
                except ValueError:
                    pass
            if cancel is not None and cancel.is_set():
                p.terminate()
                p.wait()
                raise Cancelled()
        rc = p.wait()
        if rc != 0:
            errf.seek(0)
            raise RuntimeError(T("ffmpeg_fail") + errf.read().decode("utf-8", "replace")[-2500:])
    finally:
        errf.close()


def _esc(p):
    return p.replace("\\", "/").replace("'", "'\\''")


def _grab_frame(ffmpeg, video, t):
    cmd = [ffmpeg, "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", video, "-frames:v", "1",
           "-f", "image2pipe", "-vcodec", "png", "-"]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_popen_kw())
    if res.returncode != 0 or not res.stdout:
        return None
    return Image.open(io.BytesIO(res.stdout)).convert("RGBA")


def _checker(w, h, s):
    img = Image.new("RGBA", (w, h), (60, 60, 60, 255))
    d = ImageDraw.Draw(img)
    for yy in range(0, h, s):
        for xx in range((yy // s) % 2 * s, w, 2 * s):
            d.rectangle([xx, yy, xx + s - 1, yy + s - 1], fill=(150, 150, 150, 255))
    return img


# ----------------------------------------------------------------------------- YouTube chat download
def default_download_dir():
    d = os.path.join(os.path.expanduser("~"), "Downloads")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def _strip_ansi(s):
    s = re.sub(r"\x1b\[[0-9;]*m", "", str(s)).strip()
    return re.sub(r"^(ERROR:\s*)+", "", s)


def _find_chat_file(folder, vid, since=0.0):
    best, best_t = None, -1.0
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    for n in names:
        if not n.endswith(".live_chat.json"):
            continue
        if vid and f"[{vid}]" not in n:
            continue
        p = os.path.join(folder, n)
        t = os.path.getmtime(p)
        if (vid or t >= since) and t > best_t:
            best, best_t = p, t
    return best


class _YdlLogger:
    def __init__(self):
        self.errors = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.errors.append(_strip_ansi(msg))


BROWSERS = ["chrome", "edge", "firefox", "brave", "vivaldi", "opera", "safari", "chromium"]


def export_cookies_from_browser(browser, dest_path, log=print):
    """Đọc cookie của trình duyệt (yt-dlp) và ghi ra file cookies.txt (định dạng Netscape).
    Đóng hẳn trình duyệt trước khi gọi hàm này nếu trình duyệt đang khoá file cookie.
    Reads the browser's cookies via yt-dlp and writes them to a Netscape-format cookies.txt.
    Close the browser first if it's holding an exclusive lock on its cookie database."""
    try:
        from yt_dlp.cookies import extract_cookies_from_browser, YoutubeDLCookieJar
    except ImportError:
        raise RuntimeError(T("dl_noytdlp"))
    log(T("ck_start", b=browser))
    jar = extract_cookies_from_browser(browser)
    # Chỉ giữ cookie của youtube.com: file nằm trên đĩa dạng chữ thường nên càng ít phiên đăng nhập
    # trong đó càng tốt. Only keep youtube.com cookies: the file sits on disk in plain text, so the
    # smaller the login session stored in it, the better.
    kept = YoutubeDLCookieJar()
    for c in jar:
        if "youtube.com" in (c.domain or ""):
            kept.set_cookie(c)
    if len(kept) == 0:
        raise RuntimeError(T("ck_none", b=browser))
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    kept.save(dest_path, ignore_discard=True, ignore_expires=True)
    log(T("ck_done", n=len(kept), p=dest_path))
    return dest_path


# ---- Kết nối trực tiếp với tiện ích mở rộng trình duyệt (native messaging), chỉ Windows ----
# Direct link to the browser extension (native messaging), Windows only.
#
# Chrome tự khởi chạy app này làm "native host" khi tiện ích gọi connectNative(): tiến trình
# con đó mở một cổng TCP cục bộ (127.0.0.1, cổng ngẫu nhiên) và ghi {port, token} vào relay.json.
# App (cửa sổ chính) chỉ đóng vai client: đọc relay.json rồi kết nối khi người dùng bấm "Lấy cookies".
# Nhờ vậy không có tiến trình nào tự khởi động lặp lại khi trình duyệt chưa mở tiện ích.
#
# Chrome launches this app as the "native host" when the extension calls connectNative(): that
# child process opens a local TCP port (127.0.0.1, random port) and writes {port, token} to
# relay.json. The main app window is only ever a client: it reads relay.json and connects when the
# user presses "Get cookies". Nothing respawns on its own while the extension isn't connected.

NATIVE_HOST_NAME = "com.chatoverlay.native_host"
EXTENSION_ID = "kmmooalecgnnejbbmniogbljiikjcnoh"


def _native_app_data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ChatOverlay")


def _relay_info_path():
    return os.path.join(_native_app_data_dir(), "relay.json")


def _native_host_manifest_path():
    return os.path.join(_native_app_data_dir(), "native_host.json")


def register_native_host():
    """Đăng ký native messaging host cho Chrome/Edge trong registry (chỉ Windows, bỏ qua lặng lẽ
    nếu lỗi). Gọi mỗi lần mở GUI để tự sửa nếu người dùng di chuyển thư mục app.
    Registers the native messaging host for Chrome/Edge in the registry (Windows only, fails
    silently). Called on every GUI start so it self-heals if the app folder moves."""
    if os.name != "nt":
        return
    try:
        import winreg
        if FROZEN:
            exe = sys.executable
        else:
            # Chrome chỉ gọi thẳng 1 executable (không qua "python x.py"), nên cần 1 file .bat chuyển tiếp.
            # Chrome can only exec a single executable (no "python x.py"), so forward through a .bat.
            pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.isfile(pyw):
                pyw = sys.executable
            exe = os.path.join(_native_app_data_dir(), "native_host.bat")
            os.makedirs(os.path.dirname(exe), exist_ok=True)
            with open(exe, "w", encoding="utf-8") as f:
                f.write('@echo off\r\n"%s" "%s" %%*\r\n' % (pyw, os.path.abspath(__file__)))
        manifest = {"name": NATIVE_HOST_NAME, "description": "ChatOverlay native messaging host (cookie export)",
                    "path": exe, "type": "stdio", "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"]}
        mpath = _native_host_manifest_path()
        os.makedirs(os.path.dirname(mpath), exist_ok=True)
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        for browser_key in (r"Software\Google\Chrome\NativeMessagingHosts",
                            r"Software\Microsoft\Edge\NativeMessagingHosts"):
            try:
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, browser_key + "\\" + NATIVE_HOST_NAME)
                winreg.SetValue(key, "", winreg.REG_SZ, mpath)
                winreg.CloseKey(key)
            except OSError:
                pass
    except Exception:
        pass


def run_native_host():
    """Chạy ở chế độ "native host": Chrome khởi chạy tiến trình này với stdin/stdout nối vào tiện
    ích (giao thức length-prefixed JSON). Mở cổng TCP cục bộ, chuyển tiếp yêu cầu "export" từ app
    chính sang tiện ích rồi trả kết quả về. Runs in "native host" mode: Chrome launches this
    process with stdin/stdout wired to the extension (length-prefixed JSON protocol). Opens a local
    TCP port, relays "export" requests from the main app to the extension and returns the result."""
    import socket
    import struct
    import secrets
    import time as _time

    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    io_lock = threading.Lock()

    def read_msg():
        raw_len = stdin.read(4)
        if len(raw_len) < 4:
            return None
        n = struct.unpack("<I", raw_len)[0]
        data = b""
        while len(data) < n:
            chunk = stdin.read(n - len(data))
            if not chunk:
                return None
            data += chunk
        return json.loads(data.decode("utf-8"))

    def write_msg(obj):
        data = json.dumps(obj).encode("utf-8")
        stdout.write(struct.pack("<I", len(data)))
        stdout.write(data)
        stdout.flush()

    def exchange(obj):
        with io_lock:
            write_msg(obj)
            return read_msg()

    token = secrets.token_hex(16)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    port = srv.getsockname()[1]
    relay_path = _relay_info_path()
    try:
        os.makedirs(os.path.dirname(relay_path), exist_ok=True)
        with open(relay_path, "w", encoding="utf-8") as f:
            json.dump({"port": port, "token": token}, f)
    except OSError:
        pass

    stop = threading.Event()

    def handle_client(conn):
        try:
            conn.settimeout(15)
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk
            req = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
            if req.get("token") != token or req.get("cmd") != "export":
                conn.sendall((json.dumps({"ok": False, "error": "unauthorized"}) + "\n").encode("utf-8"))
                return
            reply = exchange({"cmd": "export"})
            if reply is None:
                stop.set()
                reply = {"ok": False, "error": "extension disconnected"}
            conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))
        except Exception as e:
            try:
                conn.sendall((json.dumps({"ok": False, "error": str(e)}) + "\n").encode("utf-8"))
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def accept_loop():
        srv.settimeout(1.0)
        while not stop.is_set():
            try:
                conn, _addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            handle_client(conn)

    def keepalive_loop():
        while not stop.is_set():
            _time.sleep(25)
            if stop.is_set() or exchange({"cmd": "ping"}) is None:
                stop.set()
                break

    threading.Thread(target=accept_loop, daemon=True).start()
    threading.Thread(target=keepalive_loop, daemon=True).start()
    try:
        while not stop.is_set():
            _time.sleep(0.5)
    finally:
        stop.set()
        try:
            srv.close()
        except Exception:
            pass
        try:
            os.remove(relay_path)
        except OSError:
            pass


def try_extension_export(timeout=8):
    """Thử lấy cookies qua tiện ích trình duyệt đang kết nối (không cần đóng trình duyệt).
    Trả về (text, count), hoặc None nếu không có tiện ích đang kết nối / không phản hồi kịp.
    Tries to get cookies via a currently-connected browser extension (no need to close the
    browser). Returns (text, count), or None if nothing is connected / it didn't reply in time."""
    import socket
    try:
        with open(_relay_info_path(), "r", encoding="utf-8") as f:
            info = json.load(f)
    except Exception:
        return None
    try:
        with socket.create_connection(("127.0.0.1", info["port"]), timeout=timeout) as s:
            s.sendall((json.dumps({"token": info["token"], "cmd": "export"}) + "\n").encode("utf-8"))
            s.settimeout(timeout)
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
            if not buf:
                return None
            reply = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
            if reply.get("ok") and reply.get("cookies"):
                return reply["cookies"], reply.get("count", 0)
            return None
    except OSError:
        # relay.json cũ còn sót lại (tiến trình host trước đó bị đóng đột ngột) -> dọn luôn.
        # Stale relay.json left over from a host that was closed abruptly -> clean it up.
        try:
            os.remove(_relay_info_path())
        except OSError:
            pass
        return None


def _find_cookies_file(out_dir, work_dir):
    """Tìm file cookies.txt (xuất thủ công từ trình duyệt) ở thư mục tải, thư mục làm việc hoặc cạnh app.
    Looks for a manually exported cookies.txt in the download folder, work folder, or next to the app."""
    for d in (out_dir, work_dir, SCRIPT_DIR):
        if not d:
            continue
        p = os.path.join(d, "cookies.txt")
        if os.path.isfile(p):
            return p
    return None


def download_chat(url, out_dir, log=print, progress=None, cancel=None, work_dir=""):
    """Tải live chat replay của 1 video YouTube (giống: yt-dlp --write-subs --sub-langs live_chat --skip-download)."""
    ycache = os.path.join(prepare_work_dir(work_dir), "yt-dlp-cache")
    os.makedirs(out_dir, exist_ok=True)
    log(T("dl_start", url=url))
    log(T("dl_folder", p=os.path.abspath(out_dir)))
    tmpl = os.path.join(out_dir, "%(title).90s [%(id)s].%(ext)s")
    cookies_file = _find_cookies_file(out_dir, work_dir)
    if cookies_file:
        log(T("dl_cookiefile", p=cookies_file))
    try:
        import yt_dlp
    except ImportError:
        yt_dlp = None
    if yt_dlp is not None:
        path = _download_chat_module(yt_dlp, url, tmpl, out_dir, log, progress, cancel, ycache, cookies_file)
    else:
        exe = find_tool("yt-dlp")
        if not exe:
            raise RuntimeError(T("dl_noytdlp"))
        path = _download_chat_cli(exe, url, tmpl, out_dir, log, progress, cancel, ycache, cookies_file)
    log(T("dl_done", p=path, mb=os.path.getsize(path) / 1e6))
    return path


# Mỗi yêu cầu đã được yt-dlp tự thử lại 10 lần ("retries"); nếu vẫn hỏng, tải lại đoạn đó thêm tối đa
# FRAG_RETRIES vòng nữa (tổng cộng chịu được ~10–15 phút mất mạng). / Each request already gets 10 yt-dlp
# retries; if it still fails, the same part is fetched again up to FRAG_RETRIES more rounds.
FRAG_RETRIES = 3
_NET_ERR = re.compile(r"ssl|eof|timed? ?out|connection|reset|refused|unreachable|getaddrinfo|"
                      r"remote end closed|incomplete ?read|temporarily|network", re.I)
_LIVECHAT_STATE = {"log": None, "cancel": None}


def _short_err(e):
    lines = [l.strip() for l in _strip_ansi(e).replace("[download] Got error:", "").splitlines() if l.strip()]
    msg = lines[-1] if lines else repr(e)
    return re.sub(r"\.?\s*Giving up after \d+ retries\.?", "", msg).strip()


def _is_network_error(e):
    return bool(_NET_ERR.search(str(e) or repr(e)))


def _patch_live_chat_retries(yt_dlp):
    """yt-dlp chỉ thử lại đoạn chat khi gặp lỗi HTTP; lỗi mạng (SSL EOF, timeout, reset…) làm hỏng cả lượt tải.
    Bọc _download_fragment: xoá file dở dang rồi tải lại ĐÚNG đoạn đó (không tải lại từ đầu).
    yt-dlp only retries a chat part on HTTP errors; a network error (SSL EOF, timeout…) kills the whole
    download. Wrap _download_fragment so the same part is cleaned up and fetched again."""
    try:
        from yt_dlp.downloader.youtube_live_chat import YoutubeLiveChatFD
    except Exception:
        return False
    if getattr(YoutubeLiveChatFD, "_chat_overlay_patched", False):
        return True
    orig = YoutubeLiveChatFD._download_fragment

    def patched(self, ctx, frag_url, info_dict, headers=None, request_data=None):
        attempt = 0
        while True:
            try:
                return orig(self, ctx, frag_url, info_dict, headers, request_data)
            except Cancelled:
                raise
            except Exception as e:
                cancel = _LIVECHAT_STATE["cancel"]
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                attempt += 1
                if attempt > FRAG_RETRIES or not _is_network_error(e):
                    raise
                # xoá phần tải dở: API live chat dùng POST, không "tải tiếp" được một phần
                frag = "%s-Frag%d" % (ctx["tmpfilename"], ctx["fragment_index"])
                for f in (self.temp_name(frag), frag):
                    self.try_remove(f)
                wait = min(2 ** attempt, 30)
                log = _LIVECHAT_STATE["log"]
                if log:
                    log(T("dl_retry", i=ctx.get("fragment_index", "?"), e=_short_err(e)[:110],
                          n=attempt, m=FRAG_RETRIES, s=wait))
                for _ in range(wait * 10):
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    time.sleep(0.1)

    YoutubeLiveChatFD._download_fragment = patched
    YoutubeLiveChatFD._chat_overlay_patched = True
    return True


def _download_chat_module(yt_dlp, url, tmpl, out_dir, log, progress, cancel, ycache, cookies_file=None):
    def hook(d):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if progress and d.get("downloaded_bytes") is not None:
            progress("chat", float(d.get("downloaded_bytes") or 0))

    ylog = _YdlLogger()
    base_opts = {"skip_download": True, "writesubtitles": True, "subtitleslangs": ["live_chat"],
                 "outtmpl": tmpl, "noplaylist": True, "quiet": True, "no_warnings": True, "noprogress": True,
                 "logger": ylog, "progress_hooks": [hook], "cachedir": ycache, "ignore_no_formats_error": True,
                 "retries": 10, "fragment_retries": 10, "extractor_retries": 5, "socket_timeout": 30,
                 "retry_sleep_functions": {"http": lambda n: min(2 ** n, 30),
                                           "fragment": lambda n: min(2 ** n, 30),
                                           "extractor": lambda n: min(2 ** n, 30)}}
    # Thứ tự thử cookies: file cookies.txt xuất thủ công (đáng tin nhất) -> Chrome đang mở -> không cookies.
    # Cookie order: manually exported cookies.txt (most reliable) -> live Chrome -> no cookies.
    attempts = [("file", cookies_file)] if cookies_file else []
    attempts += [("chrome", ("chrome",)), ("none", None)]
    _patch_live_chat_retries(yt_dlp)
    _LIVECHAT_STATE.update(log=log, cancel=cancel)
    try:
        for i, (kind, cookies) in enumerate(attempts):
            last_try = i == len(attempts) - 1
            opts = dict(base_opts)
            if kind == "file":
                opts["cookiefile"] = cookies
            elif kind == "chrome":
                opts["cookiesfrombrowser"] = cookies
            ylog.errors.clear()
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True) or {}
                break
            except Cancelled:
                raise
            except Exception as e:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                msg = _strip_ansi(e) or (ylog.errors[-1] if ylog.errors else repr(e))
                if kind != "none" and not last_try and "cookie" in msg.lower():
                    log(T("dl_cookie_fail", e=_short_err(msg)[:200]))
                    continue
                if _is_network_error(msg):
                    raise RuntimeError(T("dl_net", e=_short_err(msg)[:160]))
                raise RuntimeError(T("dl_fail", e=msg, upd=T("upd_exe" if FROZEN else "upd_pip")))
    finally:
        _LIVECHAT_STATE.update(log=None, cancel=None)
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    if info.get("_type") in ("playlist", "multi_video"):
        raise RuntimeError(T("dl_playlist"))
    log(f"   Video: {info.get('title', '')}")
    sub = (info.get("requested_subtitles") or {}).get("live_chat") or {}
    path = sub.get("filepath")
    if not path or not os.path.isfile(path):
        path = _find_chat_file(out_dir, info.get("id", ""))
    if not path:
        raise RuntimeError(T("dl_nochat"))
    return path


def _run_ytdlp_cli(exe, url, tmpl, out_dir, progress, cancel, ycache, cookies_from_browser=None, cookies_file=None):
    t0 = time.time()
    cmd = [exe, "--skip-download", "--write-subs", "--sub-langs", "live_chat", "--no-playlist",
           "--newline", "--no-colors", "--cache-dir", ycache, "--ignore-no-formats-error"]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    elif cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    cmd += ["--retries", "10", "--fragment-retries", "10",
            "--socket-timeout", "30", "--retry-sleep", "exp=1:30", "-o", tmpl, url]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         **_popen_kw())
    vid, errors = "", []
    for raw in p.stdout:
        line = raw.decode("utf-8", "replace").strip()
        m = re.search(r"\[youtube\] ([\w-]{11}):", line)
        if m:
            vid = m.group(1)
        if line.startswith("ERROR"):
            errors.append(_strip_ansi(line))
        m = re.search(r"([\d.]+)\s*(KiB|MiB|GiB)", line)
        if m and progress and line.startswith("[download]"):
            mult = {"KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3}[m.group(2)]
            progress("chat", float(m.group(1)) * mult)
        if cancel is not None and cancel.is_set():
            p.terminate()
            p.wait()
            raise Cancelled()
    rc = p.wait()
    path = _find_chat_file(out_dir, vid, since=t0 - 2)
    return path, rc, errors


def _download_chat_cli(exe, url, tmpl, out_dir, log, progress, cancel, ycache, cookies_file=None):
    attempts = [{"cookies_file": cookies_file}] if cookies_file else []
    attempts += [{"cookies_from_browser": "chrome"}, {}]
    path, rc, errors = None, 0, []
    for i, kw in enumerate(attempts):
        path, rc, errors = _run_ytdlp_cli(exe, url, tmpl, out_dir, progress, cancel, ycache, **kw)
        if path or i == len(attempts) - 1 or rc == 0 or not errors or "cookie" not in errors[-1].lower():
            break
        log(T("dl_cookie_fail", e=_short_err(errors[-1])[:200]))
    if not path:
        if rc != 0 and errors:
            net = _is_network_error(errors[-1])
            raise RuntimeError(T("dl_net", e=_short_err(errors[-1])) if net else
                               T("dl_fail", e=errors[-1], upd=T("upd_exe" if FROZEN else "upd_pip")))
        raise RuntimeError(T("dl_nochat"))
    return path


# ----------------------------------------------------------------------------- yt-dlp update
# Bản yt-dlp trong app/.exe đứng yên, nhưng YouTube đổi liên tục. App tải file yt-dlp (zipapp) chính thức từ GitHub vào
# thư mục cạnh settings.json; lần mở sau nạp nó thay cho bản đóng gói. Tự kiểm tra mỗi 30 ngày + nút bấm tay.
# The bundled yt-dlp is frozen but YouTube keeps changing. The app downloads the official yt-dlp zipapp from GitHub into a
# folder next to settings.json and uses it instead of the bundled one on next launch. Auto-check every 30 days + a button.
YTDLP_REPO = "yt-dlp/yt-dlp"
UPDATE_DAYS = 30


def ytdlp_update_dir():
    return os.path.join(os.path.dirname(_settings_path()), "yt-dlp-update")


def _vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v)))


def _override_zip():
    d = ytdlp_update_dir()
    try:
        names = [n for n in os.listdir(d) if re.fullmatch(r"yt-dlp-[\d.]+\.zip", n)]
    except OSError:
        return None, ""
    if not names:
        return None, ""
    best = max(names, key=lambda n: _vkey(n[7:-4]))
    return os.path.join(d, best), best[7:-4]


class _YtdlpFinder:
    def __init__(self, zi):
        self.zi = zi

    def find_spec(self, name, path=None, target=None):
        if name == "yt_dlp" or name.startswith("yt_dlp."):
            return self.zi.find_spec(name)
        return None


def install_ytdlp_override():
    """Chạy lúc nạp module, trước mọi `import yt_dlp`. Trả về số phiên bản nếu đang dùng bản đã cập nhật."""
    z, ver = _override_zip()
    if not z or "yt_dlp" in sys.modules:
        return ""
    if not FROZEN:                       # chạy từ mã nguồn: bản pip mới hơn thì dùng pip / source run: prefer a newer pip copy
        try:
            import importlib.metadata as md
            if _vkey(md.version("yt-dlp")) >= _vkey(ver):
                return ""
        except Exception:
            pass
    try:
        import zipimport
        sys.meta_path.insert(0, _YtdlpFinder(zipimport.zipimporter(z)))
    except Exception:
        return ""
    return ver


YTDLP_OVERRIDE = install_ytdlp_override()


def _http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "ChatOverlay"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def ytdlp_current_version():
    import yt_dlp.version
    return yt_dlp.version.__version__


def ytdlp_latest_version():
    data = json.loads(_http_get(f"https://api.github.com/repos/{YTDLP_REPO}/releases/latest").decode("utf-8"))
    return str(data["tag_name"])


def ytdlp_download_update(tag):
    """Tải yt-dlp `tag`, kiểm SHA-256 với file SHA2-256SUMS của cùng bản phát hành, rồi cất vào thư mục cập nhật."""
    import hashlib
    import zipfile
    base = f"https://github.com/{YTDLP_REPO}/releases/download/{tag}/"
    blob = _http_get(base + "yt-dlp", 180)
    want = ""
    for line in _http_get(base + "SHA2-256SUMS").decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == "yt-dlp":
            want = parts[0].lower()
    if not want or hashlib.sha256(blob).hexdigest() != want:
        raise RuntimeError(T("yu_bad"))
    d = ytdlp_update_dir()
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, "download.tmp")
    with open(tmp, "wb") as f:
        f.write(blob)
    try:
        with zipfile.ZipFile(tmp) as z:
            if "yt_dlp/version.py" not in z.namelist():
                raise RuntimeError(T("yu_bad"))
    except zipfile.BadZipFile:
        raise RuntimeError(T("yu_bad"))
    new = os.path.join(d, f"yt-dlp-{tag}.zip")
    os.replace(tmp, new)
    for n in os.listdir(d):                                  # chỉ giữ bản mới nhất / keep only the newest
        if re.fullmatch(r"yt-dlp-[\d.]+\.zip", n) and os.path.join(d, n) != new:
            try:
                os.remove(os.path.join(d, n))
            except OSError:
                pass     # đang được nạp -> xoá lần sau / still in use -> next time
    return new


# ----------------------------------------------------------------------------- video download
# Tab "Tải video": xem danh sách định dạng (như yt-dlp --list-formats) -> chọn AV1 nét nhất; không có AV1 thì VP9
# nét nhất rồi đổi sang H.264 (NVENC) thành *_final.mp4 cho DaVinci/Premiere.
# "Download video" tab: read the format list (like yt-dlp --list-formats) -> best AV1; no AV1 -> best VP9, then
# convert to H.264 (NVENC) as *_final.mp4 for DaVinci/Premiere.
# Thông số theo yêu cầu người dùng, giữ nguyên / the user's own parameters, kept verbatim:
FINAL_V_ARGS = ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-rc", "vbr_hq", "-b:v", "15M",
                "-maxrate", "20M", "-bufsize", "30M"]
FINAL_CPU_ARGS = ["-c:v", "libx264", "-preset", "slow", "-b:v", "15M", "-maxrate", "20M", "-bufsize", "30M"]
FINAL_A_ARGS = ["-c:a", "aac", "-b:a", "320k"]


def _fcodec(f):
    v = (f.get("vcodec") or "none").lower()
    if v.startswith("av01"):
        return "av1"
    if v.startswith(("vp09", "vp9")):
        return "vp9"
    if v.startswith("avc1"):
        return "h264"
    return ""


def _fq(f):
    return (f.get("height") or 0, f.get("fps") or 0, f.get("tbr") or 0)


def _is_premium(f):
    return "premium" in str(f.get("format_note") or "").lower()


def _fdesc(f):
    fps = int(round(f.get("fps") or 0))
    prem = " Premium" if _is_premium(f) else ""
    return f"{f.get('height') or '?'}p{fps if fps > 30 else ''} {_fcodec(f) or f.get('vcodec')}{prem} ({f.get('format_id')})"


def format_table(info):
    """Bảng định dạng giống `yt-dlp --list-formats` (rút gọn). / A shortened `yt-dlp --list-formats` table."""
    rows = ["  ID      EXT   RES        FPS  CODEC          SIZE / TBR"]
    for f in info.get("formats") or []:
        if f.get("vcodec") in (None, "none") and f.get("acodec") in (None, "none"):
            continue                                   # ảnh xem trước (storyboard) / storyboards
        kind = "video" if f.get("acodec") in (None, "none") else ("audio" if f.get("vcodec") in (None, "none") else "v+a")
        res = f"{f.get('width') or ''}x{f.get('height')}" if f.get("height") else "audio only"
        size = f.get("filesize") or f.get("filesize_approx")
        rows.append("  %-7s %-5s %-10s %-4s %-14s %s %s" % (
            f.get("format_id", ""), f.get("ext", ""), res, int(f.get("fps") or 0) or "",
            (f.get("vcodec") if kind != "audio" else f.get("acodec")) or "", f"{size / 1e6:.0f}MB" if size else "",
            f"{int(f.get('tbr') or 0)}k {kind}"))
    return "\n".join(rows)


def choose_video_formats(info, max_h=0, force="", kind="both", premium=True):
    """Chọn định dạng hình + tiếng. Trả về dict {mode, video, audio, container, note}.
    mode: 'av1' (giữ nguyên) | 'vp9' (đổi sang H.264) | 'h264' (giữ nguyên, YouTube không có AV1/VP9).
    Pick the video + audio formats. mode: 'av1' (keep as is) | 'vp9' (convert to H.264) | 'h264' (keep as is).
    kind: 'both' (hình+tiếng) | 'video' (chỉ hình) | 'audio' (chỉ tiếng, mode='audio').
    premium=True: có bản Premium nét bằng/hơn bản thường thì chọn nó (mode='premium', đổi sang H.264 như VP9).
    premium=True: a Premium format at least as sharp as the best normal one wins (mode='premium', converted to H.264 like VP9)."""
    fmts = info.get("formats") or []

    def ok(f):
        return (not f.get("has_drm") and "premium" not in str(f.get("format_note") or "").lower()
                and (f.get("protocol") or "") not in ("mhtml",))
    auds = [f for f in fmts if ok(f) and f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none")
            and "drc" not in str(f.get("format_id"))]       # bỏ bản tiếng nén động (DRC) / skip dynamic-range-compressed audio

    def aq(f):                                       # ưu tiên bản tiếng gốc (video nhiều ngữ) / prefer the original language
        return (f.get("language_preference") or 0, f.get("abr") or f.get("tbr") or 0)
    m4a = [f for f in auds if f.get("ext") == "m4a"]
    if kind != "video" and not auds:
        raise RuntimeError(T("vd_noformat"))
    if kind == "audio":                              # m4a (AAC) nạp thẳng vào phần mềm dựng, giữ nguyên chất lượng gốc
        return {"mode": "audio", "video": None, "audio": max(m4a or auds, key=aq), "container": None,
                "note": "" if m4a else T("vd_audio_noaac")}
    def video_only(f):
        return _fcodec(f) and f.get("acodec") in (None, "none") and f.get("height") and not f.get("has_drm")

    def cap(vs):
        sdr = [f for f in vs if (f.get("dynamic_range") or "SDR") == "SDR"]  # HDR làm hỏng màu khi đổi H.264
        vs = sdr or vs
        if max_h and vs:                                                     # trần độ phân giải / resolution cap
            low = [f for f in vs if f["height"] <= max_h]
            vs = low or [f for f in vs if f["height"] == min(g["height"] for g in vs)]
        return vs
    vids = [f for f in fmts if ok(f) and video_only(f)]
    prem = cap([f for f in fmts if premium and video_only(f) and _is_premium(f)]) if kind != "audio" else []
    if not vids and not prem:
        raise RuntimeError(T("vd_noformat"))
    vids = cap(vids)
    vids = [f for f in vids if "m3u8" not in str(f.get("protocol"))] or vids  # ưu tiên tải thẳng, không HLS
    best = {}
    for c in ("av1", "vp9", "h264"):
        cand = [f for f in vids if _fcodec(f) == c]
        if cand:
            best[c] = max(cand, key=_fq)
    force = (force or os.environ.get("CHAT_OVERLAY_FORCE_CODEC", "")).lower()   # chỉ để kiểm thử / test only
    note = ""
    if force in best:
        mode = force
    elif "av1" in best and ("vp9" not in best or _fq(best["av1"])[0] >= _fq(best["vp9"])[0]):
        mode = "av1"
    elif "vp9" in best:
        mode = "vp9"
        if "av1" in best:
            note = T("vd_av1_lower", a=_fdesc(best["av1"]), v=_fdesc(best["vp9"]))
    elif best:
        mode = "h264"
    if prem and force not in best:
        bp = max(prem, key=_fq)
        if not best or _fq(bp)[0] >= max(_fq(f)[0] for f in best.values()):
            best["premium"], mode, note = bp, "premium", ""
    if kind == "video":
        return {"mode": mode, "video": best[mode], "audio": None, "container": None, "note": note}
    if mode not in ("vp9", "premium") and m4a:       # AAC trong MP4: DaVinci/Premiere đọc chắc chắn / AAC in MP4: safest
        audio, container = max(m4a, key=aq), "mp4"
    else:
        audio, container = max(auds, key=aq), "mkv"
    return {"mode": mode, "video": best[mode], "audio": audio, "container": container, "note": note}


def _final_path(src):
    return os.path.splitext(src)[0] + "_final.mp4"


def _video_cookie_attempts(cookies_file):
    att = [("file", cookies_file)] if cookies_file else []
    return att + [("chrome", ("chrome",)), ("none", None)]


def _log_choice(choice, want, log):
    """Ghi dòng "▶ Chọn …" (định dạng sẽ tải). / Log the "▶ Picked …" line (the formats to be downloaded)."""
    v, a = choice["video"], choice["audio"]
    adesc = f"{a.get('ext')} {int(a.get('abr') or 0)}k ({a.get('format_id')})" if a else T("vd_noaudio")
    if choice["mode"] == "audio":
        log(T("vd_pick_audio", a=adesc))
    elif want == "video":
        log(T("vd_pick_video", v=_fdesc(v), k=T("vd_will_conv" if choice["mode"] in ("vp9", "premium") else "vd_keep")))
    else:
        log(T("vd_pick_" + choice["mode"], v=_fdesc(v), a=adesc))
    if choice["note"]:
        log(choice["note"])


def _format_verdict(info, table, max_h, want, log):
    """Nút "Kiểm tra định dạng": in bảng định dạng + kết luận đã tải được chưa. Trả về câu kết luận (1 dòng).
    "Check formats" button: print the format table + whether it can be downloaded yet. Returns a one-line verdict."""
    st = info.get("live_status") or ""
    if info.get("is_live") or st == "is_live":
        verdict = T("vc_live")
    elif st == "is_upcoming":
        verdict = T("vc_upcoming")
    else:
        if info.get("formats"):
            log(table or format_table(info))
        try:
            choice = choose_video_formats(info, max_h, kind=want)
        except RuntimeError:
            choice = None
        if choice is None:
            verdict = T("vc_none")
        else:
            have = []
            for pr in (False, True):
                for c in ("av1", "vp9", "h264"):
                    hs = [f.get("height") or 0 for f in info.get("formats") or []
                          if _fcodec(f) == c and f.get("acodec") in (None, "none") and _is_premium(f) == pr]
                    if hs:
                        have.append(c.upper() + (" Premium" if pr else "") + f" {max(hs)}p")
            log(T("vc_have", s=", ".join(have) or "—"))
            log(T("vc_ifnow"))
            _log_choice(choice, want, log)
            v = choice["video"]
            if v is not None and choice["mode"] != "premium" and "m3u8" in str(v.get("protocol")):
                log(T("vc_hls"))
            if choice["mode"] == "audio":
                verdict = T("vc_ok_audio")
            elif choice["mode"] == "premium":
                verdict = T("vc_ok_premium", v=_fdesc(v))
            elif choice["mode"] == "av1":
                verdict = T("vc_ok_av1", v=_fdesc(v))
            else:
                verdict = T("vc_no_av1", v=_fdesc(v))
        if st == "post_live":
            log(T("vc_post_live"))
    log(verdict)
    return verdict


def download_video(url, out_dir, max_h=0, delete_src=False, log=print, progress=None, cancel=None, work_dir="",
                   kind="both", list_only=False):
    """Tải video (AV1 hoặc VP9→H.264). Trả về đường dẫn file cuối.
    list_only=True: chỉ in bảng định dạng (yt-dlp --list-formats) + kết luận, không tải; trả về câu kết luận.
    Download a video; returns the final file path. list_only=True: only list formats + verdict, returns the verdict."""
    want = kind                  # biến `kind` bên dưới dùng cho vòng thử cookies / `kind` is reused by the cookie loop below
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError(T("dl_noytdlp"))
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg and not list_only:
        raise RuntimeError(T("no_ffmpeg"))
    ycache = os.path.join(prepare_work_dir(work_dir), "yt-dlp-cache")
    if not list_only:
        os.makedirs(out_dir, exist_ok=True)
        log(T("dl_folder", p=os.path.abspath(out_dir)))
    cookies_file = _find_cookies_file(out_dir, work_dir)
    if cookies_file:
        log(T("dl_cookiefile", p=cookies_file))
    ylog = _YdlLogger()
    state = {"done": {}, "total": 0.0, "n": 0}

    def check_cancel():
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    def dl_hook(d):
        check_cancel()
        if d.get("status") != "downloading" or not progress:
            return
        fid = (d.get("info_dict") or {}).get("format_id") or d.get("filename")
        state["done"][fid] = float(d.get("downloaded_bytes") or 0)
        total = state["total"] or float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
        if total > 0:
            progress("vdl", min(1.0, sum(state["done"].values()) / total))

    def pp_hook(d):
        check_cancel()
        if d.get("status") == "started" and progress and d.get("postprocessor") in ("Merger", "FFmpegMerger"):
            progress("vmerge", -1)

    base = {"quiet": True, "no_warnings": True, "noprogress": True, "logger": ylog, "noplaylist": True,
            "cachedir": ycache, "ffmpeg_location": os.path.dirname(ffmpeg) if ffmpeg else None,
            "retries": 10, "fragment_retries": 10, "extractor_retries": 5, "socket_timeout": 30,
            "retry_sleep_functions": {k: (lambda n: min(2 ** n, 30)) for k in ("http", "fragment", "extractor")}}
    if list_only:            # live vừa kết thúc/chưa bắt đầu: không có định dạng vẫn đọc được thông tin, không báo lỗi
        base["ignore_no_formats_error"] = True   # / just-ended or upcoming live: read the info even with no formats
    attempts = _video_cookie_attempts(cookies_file)
    table = ""
    info, used, choice = None, None, None
    if progress:
        progress("vlist", -1)
    log(T("vd_listing"))
    for i, (kind, cookies) in enumerate(attempts):
        opts = dict(base)
        if kind == "file":
            opts["cookiefile"] = cookies
        elif kind == "chrome":
            opts["cookiesfrombrowser"] = cookies
        ylog.errors.clear()
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False) or {}
                if list_only and info.get("formats"):
                    try:                       # đúng bảng của `yt-dlp --list-formats` / the exact --list-formats table
                        table = _strip_ansi(ydl.render_formats_table(info) or "")
                    except Exception:
                        table = ""
            used = opts
            break
        except Cancelled:
            raise
        except Exception as e:
            check_cancel()
            msg = _strip_ansi(e) or (ylog.errors[-1] if ylog.errors else repr(e))
            if kind != "none" and i < len(attempts) - 1 and "cookie" in msg.lower():
                log(T("dl_cookie_fail", e=_short_err(msg)[:200]))
                continue
            if _is_network_error(msg):
                raise RuntimeError(T("vd_net", e=_short_err(msg)[:160]))
            raise RuntimeError(T("vd_fail", e=msg, upd=T("upd_app")))
    check_cancel()
    if info.get("_type") in ("playlist", "multi_video"):
        raise RuntimeError(T("dl_playlist"))
    if info.get("is_live") and not list_only:
        raise RuntimeError(T("vd_live"))
    log(f"   Video: {info.get('title', '')}")
    if list_only:
        return _format_verdict(info, table, max_h, want, log)
    log(format_table(info))
    choice = choose_video_formats(info, max_h, kind=want)
    v, a = choice["video"], choice["audio"]
    _log_choice(choice, want, log)
    suffix = {"both": "", "video": "_video", "audio": "_audio"}[want]   # không đè lên file hình+tiếng đã tải / don't clash
    while True:
        picked = [f for f in (v, a) if f]
        state["total"] = float(sum((f.get("filesize") or f.get("filesize_approx") or 0) for f in picked))
        state["done"].clear()
        opts = dict(used)
        opts.update({"format": "+".join(f["format_id"] for f in picked),
                     "outtmpl": os.path.join(out_dir, "%(title).90s [%(id)s]" + suffix + ".%(ext)s"), "continuedl": True,
                     "progress_hooks": [dl_hook], "postprocessor_hooks": [pp_hook], "overwrites": False})
        if len(picked) == 2:
            opts["merge_output_format"] = choice["container"]
        ylog.errors.clear()
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                res = ydl.extract_info(url, download=True) or {}
            break
        except Cancelled:
            raise
        except Exception as e:
            check_cancel()
            msg = _strip_ansi(e) or (ylog.errors[-1] if ylog.errors else repr(e))
            if _is_network_error(msg):
                raise RuntimeError(T("vd_net", e=_short_err(msg)[:160]))
            if choice["mode"] != "premium":
                raise RuntimeError(T("vd_fail", e=msg, upd=T("upd_app")))
            log(T("vd_prem_fail", e=_short_err(msg)[:160]))     # Premium hỏng -> bản thường / Premium failed -> normal
            choice = choose_video_formats(info, max_h, kind=want, premium=False)
            v, a = choice["video"], choice["audio"]
            _log_choice(choice, want, log)
    check_cancel()
    src = ((res.get("requested_downloads") or [{}])[0]).get("filepath") or ""
    if not os.path.isfile(src):
        raise RuntimeError(T("vd_nofile"))
    log(T("vd_downloaded", p=src, mb=os.path.getsize(src) / 1e6))
    if choice["mode"] not in ("vp9", "premium"):
        return src
    final = _final_path(src)
    convert_to_final(ffmpeg, src, final, float(info.get("duration") or 0), log, progress, cancel)
    if delete_src:
        try:
            os.remove(src)
            log(T("vd_src_deleted", p=src))
        except OSError:
            pass
    return final


def convert_to_final(ffmpeg, src, dst, duration, log=print, progress=None, cancel=None):
    """VP9 → H.264 + AAC (*_final.mp4). Ghi ra file .part rồi đổi tên, nên file dở dang không bị nhầm là xong.
    VP9 → H.264 + AAC. Writes to a .part file then renames, so an interrupted file is never mistaken for a finished one."""
    gpu = _encoder_works(ffmpeg, "h264_nvenc")
    log(T("vd_conv", e="h264_nvenc (GPU)" if gpu else "libx264 (CPU)", p=dst))
    if not gpu:
        log(T("vd_conv_cpu"))
    tmp = dst + ".part.mp4"
    cmd = ([ffmpeg, "-y", "-v", "error", "-nostdin", "-progress", "pipe:1", "-i", src, "-map", "0:v:0", "-map", "0:a:0?"]
           + (FINAL_V_ARGS if gpu else FINAL_CPU_ARGS) + ["-pix_fmt", "yuv420p"] + FINAL_A_ARGS
           + ["-movflags", "+faststart", tmp])
    try:
        run_ffmpeg(cmd, duration, progress, cancel, log)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    log(T("vd_final", p=dst, mb=os.path.getsize(dst) / 1e6))


ENCODER_ORDER = ["av1_nvenc", "hevc_nvenc", "av1_qsv", "hevc_qsv", "hevc_amf", "hevc_videotoolbox",
                 "h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox", "libx264"]


def encoder_args(name):
    """Thiết lập chất lượng cao (gần như không thấy khác bản gốc) cho từng bộ mã hoá."""
    table = {
        "av1_nvenc": ["-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", "28", "-b:v", "0"],
        "hevc_nvenc": ["-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", "24", "-b:v", "0", "-tag:v", "hvc1"],
        "h264_nvenc": ["-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", "21", "-b:v", "0"],
        "av1_qsv": ["-preset", "medium", "-global_quality", "28"],
        "hevc_qsv": ["-preset", "medium", "-global_quality", "24", "-tag:v", "hvc1"],
        "h264_qsv": ["-preset", "medium", "-global_quality", "21"],
        "hevc_amf": ["-quality", "quality", "-rc", "cqp", "-qp_i", "22", "-qp_p", "24", "-tag:v", "hvc1"],
        "h264_amf": ["-quality", "quality", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22"],
        "hevc_videotoolbox": ["-q:v", "65", "-tag:v", "hvc1"],
        "h264_videotoolbox": ["-q:v", "65"],
        "libsvtav1": ["-preset", "8", "-crf", "30"],
        "libx264": ["-preset", "veryfast", "-crf", "18"],
    }
    return ["-c:v", name] + table.get(name, table["libx264"])


def _encoder_works(ffmpeg, name):
    cmd = [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=0.2",
           "-frames:v", "3", "-pix_fmt", "yuv420p"] + encoder_args(name) + ["-f", "null", "-"]
    try:
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
                              **_popen_kw()).returncode == 0
    except Exception:
        return False


def pick_encoder(ffmpeg, pref, log=print):
    if pref and pref != "auto":
        if _encoder_works(ffmpeg, pref):
            return pref
        log(T("enc_na", e=pref))
    for name in ENCODER_ORDER:
        if _encoder_works(ffmpeg, name):
            return name
    return "libx264"


def default_output(o):
    folder = os.path.dirname(os.path.abspath(o.chat))
    base = os.path.basename(o.chat)
    base = re.sub(r"\.json$", "", base, flags=re.I)
    base = re.sub(r"[._]live_chat$", "", base, flags=re.I)
    ext = {"mov": ".mov", "prores": ".mov", "ffv1": ".mov", "webm": ".webm", "green": ".mp4", "burn": ".mp4"}[o.fmt]
    suffix = "_chat_burned" if o.fmt == "burn" else ("_chat_green" if o.fmt == "green" else "_chat_overlay")
    if (o.start or 0) > 0 or (o.end or 0) > 0:      # tên file ghi rõ đoạn thời gian, dễ khớp trong DaVinci
        suffix += f"_{_tag(o.start or 0)}-{_tag(o.end) if o.end else 'end'}"
    return os.path.join(folder, base + suffix + ext)


def resolve_output(o):
    """Đường dẫn tuyệt đối của file xuất. Tên không kèm thư mục -> lưu cạnh file chat
    (không phụ thuộc thư mục hiện hành, vốn có thể là C:\\Windows\\System32 khi mở bằng .pyw).
    Nếu người dùng nhập một thư mục -> đặt tên tự động bên trong thư mục đó."""
    auto = default_output(o)
    p = os.path.expanduser((o.output or "").strip().strip('"'))
    if not p:
        return auto
    if not os.path.isabs(p):
        p = os.path.join(os.path.dirname(os.path.abspath(o.chat)), p)
    if os.path.isdir(p) or p.endswith(("/", "\\")):
        return os.path.join(p, os.path.basename(auto))
    return os.path.abspath(p)


def check_writable(path):
    """Báo lỗi ngay từ đầu nếu không ghi được, thay vì sau khi đã dựng xong khung hình."""
    folder = os.path.dirname(path) or "."
    try:
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".chat_overlay_", dir=folder)
        os.close(fd)
        os.remove(tmp)
    except OSError as e:
        raise RuntimeError(T("no_write", p=folder, e=e.strerror or e))
    if os.path.exists(path):
        try:
            with open(path, "ab"):
                pass
        except OSError:
            raise RuntimeError(T("file_locked", p=path))


def _tag(sec):
    sec = int(round(sec))
    return f"{sec // 3600}h{sec % 3600 // 60:02d}m{sec % 60:02d}s"


# ----------------------------------------------------------------------------- parallel frame rendering
_WORKER = {}


def _worker_init(o, canvas_h, box_h, cache_dir, work_dir):
    """Mỗi tiến trình con tự dựng lại bộ vẽ (giống hệt tiến trình chính) rồi vẽ một phần khung hình."""
    noop = lambda *a, **k: None
    try:
        prepare_work_dir(work_dir)
    except Exception:
        pass
    msgs, _ = load_chat(o.chat, noop)
    schedule(msgs, o)
    g = Geometry(o, canvas_h)
    r = MsgRenderer(o, g, Fonts(o.font, o.font_bold, noop), Assets(cache_dir, False, noop), EmojiFont())
    _WORKER["comp"] = Compositor(o, g, r, msgs, box_h)


def _worker_render(jobs, folder):
    comp = _WORKER["comp"]
    for idx, key in jobs:
        comp.compose(key).save(os.path.join(folder, f"f{idx:06d}.png"), compress_level=1)
    return len(jobs)


def _cpu_workers():
    forced = os.environ.get("CHAT_OVERLAY_WORKERS", "")
    if forced.isdigit() and int(forced) > 0:
        return int(forced)
    return max(1, min(16, (os.cpu_count() or 1) - 1))


def render_unique_frames(keys, folder, comp, worker_args, progress, cancel, log):
    """Vẽ các khung hình khác nhau ra PNG f000000.png… (theo thứ tự xuất hiện), dùng nhiều nhân CPU."""
    n = len(keys)
    workers = _cpu_workers() if n >= 400 else 1
    if workers > 1:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor, as_completed
        log(T("workers", n=workers))
        chunk = max(50, min(400, n // (workers * 8) or 1))
        jobs = [[(i, keys[i]) for i in range(s, min(n, s + chunk))] for s in range(0, n, chunk)]
        done = 0
        try:
            with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                                     initializer=_worker_init, initargs=worker_args) as ex:
                futs = [ex.submit(_worker_render, j, folder) for j in jobs]
                try:
                    for f in as_completed(futs):
                        done += f.result()
                        progress("frames", done / n)
                        if cancel is not None and cancel.is_set():
                            raise Cancelled()
                except BaseException:
                    for f in futs:
                        f.cancel()
                    raise
            return
        except Cancelled:
            raise
        except Exception as e:      # ví dụ môi trường không cho tạo tiến trình con -> vẽ tuần tự
            log(T("workers_fail", e=e))
    futs = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, key in enumerate(keys):
            futs.append(ex.submit(comp.compose(key).save, os.path.join(folder, f"f{i:06d}.png"), compress_level=1))
            if len(futs) > 48:
                futs.pop(0).result()
            if i % 50 == 0:
                progress("frames", i / n)
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
        for f in futs:
            f.result()


# ----------------------------------------------------------------------------- MOV with shared duplicate frames
_MOV_CONTAINERS = {"moov", "trak", "mdia", "minf", "stbl", "dinf"}


def _parse_boxes(data):
    out, i = [], 0
    while i + 8 <= len(data):
        size = int.from_bytes(data[i:i + 4], "big")
        typ = data[i + 4:i + 8].decode("latin-1")
        hdr = 8
        if size == 1:
            size, hdr = int.from_bytes(data[i + 8:i + 16], "big"), 16
        elif size == 0:
            size = len(data) - i
        body = data[i + hdr:i + size]
        out.append([typ, _parse_boxes(body) if typ in _MOV_CONTAINERS else body])
        i += size
    return out


def _box(typ, body):
    return (8 + len(body)).to_bytes(4, "big") + typ.encode("latin-1") + body


def _serialize(boxes):
    return b"".join(_box(t, _serialize(b) if isinstance(b, list) else b) for t, b in boxes)


def _find(boxes, typ):
    return next((b for t, b in boxes if t == typ), None)


def _top_level_boxes(f):
    f.seek(0, 2)
    end, pos, res = f.tell(), 0, []
    while pos + 8 <= end:
        f.seek(pos)
        h = f.read(16)
        size, typ = int.from_bytes(h[:4], "big"), h[4:8].decode("latin-1")
        if size == 1:
            size = int.from_bytes(h[8:16], "big")
        elif size == 0:
            size = end - pos
        res.append((typ, pos, size))
        pos += size
    return res


def _set_duration(body, offs_v0, offs_v1, value):
    """Ghi trường duration trong mvhd/tkhd/mdhd (phiên bản 0: 32 bit, 1: 64 bit)."""
    b = bytearray(body)
    if b[0] == 1:
        b[offs_v1:offs_v1 + 8] = value.to_bytes(8, "big")
    else:
        b[offs_v0:offs_v0 + 4] = min(value, 0xFFFFFFFF).to_bytes(4, "big")
    return bytes(b)


def assemble_shared_mov(path, frame_to_unique):
    """File MOV `path` chứa mỗi khung hình KHÁC NHAU đúng 1 lần (đã nén). Viết lại bảng mẫu (moov) để
    video có đủ từng khung theo đúng thứ tự, các khung trùng trỏ về cùng dữ liệu – không nén lại lần nữa.
    Kết quả vẫn là MOV hằng số khung hình (CFR) bình thường."""
    from array import array
    with open(path, "r+b") as f:
        tops = _top_level_boxes(f)
        moov_t = next(t for t in tops if t[0] == "moov")
        f.seek(moov_t[1])
        raw = f.read(moov_t[2])
        moov = _parse_boxes(raw[8:])
        mvhd = _find(moov, "mvhd")
        trak = _find(moov, "trak")
        mdia = _find(trak, "mdia")
        mdhd = _find(mdia, "mdhd")
        stbl = _find(_find(mdia, "minf"), "stbl")
        # vị trí từng khung đã nén trong file
        stsz = _find(stbl, "stsz")
        fixed, count = int.from_bytes(stsz[4:8], "big"), int.from_bytes(stsz[8:12], "big")
        if fixed:
            sizes = [fixed] * count
        else:
            sizes = array("I")
            sizes.frombytes(stsz[12:12 + 4 * count])
            if sys.byteorder == "little":
                sizes.byteswap()
        co = _find(stbl, "co64")
        width = 8
        if co is None:
            co, width = _find(stbl, "stco"), 4
        nchunks = int.from_bytes(co[4:8], "big")
        chunk_off = [int.from_bytes(co[8 + width * i:8 + width * (i + 1)], "big") for i in range(nchunks)]
        stsc = _find(stbl, "stsc")
        ents = [(int.from_bytes(stsc[8 + 12 * i:12 + 12 * i], "big"), int.from_bytes(stsc[12 + 12 * i:16 + 12 * i], "big"))
                for i in range(int.from_bytes(stsc[4:8], "big"))]
        offsets, k = [], 0
        for c in range(1, nchunks + 1):
            spc = [s for fc, s in ents if fc <= c][-1]
            o = chunk_off[c - 1]
            for _ in range(spc):
                offsets.append(o)
                o += sizes[k]
                k += 1
        if len(offsets) != count:
            raise RuntimeError("MOV sample table mismatch")
        stts = _find(stbl, "stts")
        delta = int.from_bytes(stts[12:16], "big")
        media_ts = int.from_bytes(mdhd[20:24] if mdhd[0] == 1 else mdhd[12:16], "big")
        movie_ts = int.from_bytes(mvhd[20:24] if mvhd[0] == 1 else mvhd[12:16], "big")
        n = len(frame_to_unique)
        new_sizes = array("I", (sizes[u] for u in frame_to_unique))
        new_offs = array("Q", (offsets[u] for u in frame_to_unique))
        if sys.byteorder == "little":
            new_sizes.byteswap()
            new_offs.byteswap()
        zero = b"\0\0\0\0"
        new_stbl = [["stsd", _find(stbl, "stsd")],
                    ["stts", zero + (1).to_bytes(4, "big") + n.to_bytes(4, "big") + delta.to_bytes(4, "big")],
                    ["stsc", zero + (1).to_bytes(4, "big") + (1).to_bytes(4, "big") * 3],
                    ["stsz", zero + zero + n.to_bytes(4, "big") + new_sizes.tobytes()],
                    ["co64", zero + n.to_bytes(4, "big") + new_offs.tobytes()]]
        media_dur = n * delta
        movie_dur = media_dur * movie_ts // media_ts
        for box in (moov, trak, mdia):
            for item in box:
                if item[0] == "mvhd":
                    item[1] = _set_duration(item[1], 16, 24, movie_dur)
                elif item[0] == "tkhd":
                    item[1] = _set_duration(item[1], 20, 28, movie_dur)
                elif item[0] == "mdhd":
                    item[1] = _set_duration(item[1], 16, 24, media_dur)
        trak[:] = [b for b in trak if b[0] != "edts"]
        minf = _find(mdia, "minf")
        for item in minf:
            if item[0] == "stbl":
                item[1] = new_stbl
        new_moov = _box("moov", _serialize(moov))
        if moov_t is tops[-1]:
            f.seek(moov_t[1])
            f.truncate()
        else:                       # moov không nằm cuối: biến moov cũ thành 'free', ghi moov mới ở cuối
            f.seek(moov_t[1] + 4)
            f.write(b"free")
            f.seek(0, 2)
        f.write(new_moov)


# ProRes 4444 XQ, alpha 16-bit, lượng tử thấp: gần như không phân biệt được với ảnh gốc
# (đo được: sai lệch TB 0.06/255, lớn nhất 6/255 so với 76/255 của thiết lập cũ)
PRORES_ARGS = ["-c:v", "prores_ks", "-profile:v", "4444xq", "-pix_fmt", "yuva444p10le",
               "-alpha_bits", "16", "-vendor", "apl0", "-qscale:v", "2"]

FFV1_ARGS = ["-c:v", "ffv1", "-level", "3", "-pix_fmt", "bgra", "-slices", "16", "-g", "1"]


def _rate(fps):
    from fractions import Fraction
    fr = Fraction(fps).limit_denominator(1001)
    return f"{fr.numerator}/{fr.denominator}"


# ----------------------------------------------------------------------------- main pipeline
def run(o, log=print, progress=None, cancel=None):
    t_begin = time.time()

    def check():
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    prog = progress or (lambda ph, f: None)
    if not o.chat or not os.path.isfile(o.chat):
        raise RuntimeError(T("no_chat"))
    ffmpeg = find_tool("ffmpeg", o.ffmpeg)
    ffprobe = find_tool("ffprobe", o.ffmpeg)
    preview = o.preview_at is not None and o.preview_at >= 0
    if not ffmpeg and not preview:
        raise RuntimeError(T("no_ffmpeg"))
    if o.fmt == "burn" and not o.video:
        raise RuntimeError(T("burn_video"))
    out_path = resolve_output(o)
    want = {"mov": (".mov",), "prores": (".mov",), "ffv1": (".mov", ".mkv"), "webm": (".webm",),
            "green": (".mp4", ".mov", ".mkv"), "burn": (".mp4", ".mkv", ".mov")}[o.fmt]
    if os.path.splitext(out_path)[1].lower() not in want:
        out_path += want[0]
    if preview:
        out_path = os.path.splitext(out_path)[0] + f"_preview_{int(o.preview_at)}s.png"
    check_writable(out_path)

    work = prepare_work_dir(o.work_dir)
    log(T("work", p=work, gb=shutil.disk_usage(work).free / 1e9))
    log(T("s_read"))
    msgs, removed = load_chat(o.chat, log)
    if not msgs:
        raise RuntimeError(T("no_msgs"))
    kinds = {}
    for m in msgs:
        kinds[m.kind] = kinds.get(m.kind, 0) + 1
    log(T("n_msgs", n=len(msgs), kinds=", ".join(f"{k}: {v}" for k, v in kinds.items()))
        + (T("n_removed", n=removed) if removed else ""))

    cw, ch, vfps, vdur = o.width, o.height, 0.0, 0.0
    if o.video:
        if not os.path.isfile(o.video):
            raise RuntimeError(T("no_video"))
        if ffprobe:
            cw, ch, vfps, vdur = probe_video(ffprobe, o.video)
            log(T("video_info", w=cw, h=ch, fps=vfps, dur=fmt_time(vdur)))
        else:
            log(T("no_ffprobe"))
        if o.check_pair:
            why = check_pair(o.chat, o.video, msgs, vdur)
            if why:
                raise PairMismatch("\n".join([T("mm_head")] + why))
    fps = o.fps if o.fps and o.fps > 0 else (vfps or 30.0)

    maxlag, maxearly = schedule(msgs, o)
    log(T("queued", m=o.max_messages, g=o.min_gap, lag=maxlag, early=maxearly))

    g = Geometry(o, ch)
    log(T("s_assets"))
    cache_dir = o.cache_dir or os.path.join(work, "cache")
    old_cache = os.path.join(SCRIPT_DIR, "chat_cache")      # vị trí cache của bản trước
    if not o.cache_dir and os.path.isdir(old_cache) and not os.path.isdir(cache_dir):
        try:
            shutil.move(old_cache, cache_dir)
            log(T("cache_moved", p=cache_dir))
        except OSError:
            pass
    assets = Assets(cache_dir, enabled=o.download, log=log)
    urls = []
    for m in msgs:
        if o.avatars and m.avatar_url:
            urls.append(m.avatar_url)
        urls += [r.url for r in m.runs if r.kind == "emoji" and r.url]
        if m.badge_url:
            urls.append(m.badge_url)
        if m.sticker_url:
            urls.append(m.sticker_url)
    got, tot = assets.prefetch(urls, prog, cancel)
    log(T("assets", a=got, b=tot))

    fonts = Fonts(o.font, o.font_bold, log)
    renderer = MsgRenderer(o, g, fonts, assets, EmojiFont())

    log(T("s_layout"))
    heights = []
    for i, m in enumerate(msgs):
        heights.append(renderer.render(m).height)
        if i % 100 == 0:
            prog("layout", i / len(msgs))
            check()
    # chiều cao khung tự động: đủ chứa trọn vẹn max_messages tin trong 95% thời gian;
    # lúc có nhiều tin dài, tin cũ nhất sẽ mờ dần ở mép trên thay vì làm khung phình to
    win = max(1, o.max_messages)
    sums, s = [], 0
    for i, hh in enumerate(heights):
        s += hh
        if i >= win:
            s -= heights[i - win]
        sums.append(s + g.spacing * (min(i + 1, win) - 1))
    sums.sort()
    best = sums[min(len(sums) - 1, int(len(sums) * 0.95))]
    box_h = best + 2 * g.panel_pad + g.fade_h
    if o.box_height:
        box_h = int(round(o.box_height * g.S))
    box_h = min(box_h, ch - 2 * g.margin_y) if o.canvas == "full" or o.fmt == "burn" else box_h
    box_h = max(2, box_h // 2 * 2)
    bw = g.box_w
    pos = o.position
    bx = g.margin_x if "left" in pos else (cw - bw - g.margin_x if "right" in pos else (cw - bw) // 2)
    by = g.margin_y if pos.startswith("top") else (ch - box_h - g.margin_y if pos.startswith("bottom") else (ch - box_h) // 2)
    bx, by = max(0, bx), max(0, by)
    log(T("box", bw=bw, bh=box_h, x=bx, y=by, cw=cw, ch=ch))
    if o.canvas == "box" and o.fmt != "burn" and not preview:
        # DaVinci: gốc toạ độ ở giữa khung hình, trục Y hướng lên
        log(T("davinci", x=int(round(bx + bw / 2 - cw / 2)), y=int(round(ch / 2 - (by + box_h / 2))), cw=cw, ch=ch))

    comp = Compositor(o, g, renderer, msgs, box_h)
    tl = Timeline([m.show for m in msgs], heights, max(0.0, o.anim), g.spacing, win, o.hide_after)

    # ---- preview
    if preview:
        t = o.preview_at
        img = comp.compose(tl.key(t))
        bg = _grab_frame(ffmpeg, o.video, t) if (o.video and ffmpeg) else None
        if bg is None or bg.size != (cw, ch):
            bg = _checker(cw, ch, max(8, int(24 * g.S)))
        bg.alpha_composite(img, (bx, by))
        out = out_path
        bg.convert("RGB").save(out)
        log(T("prev_saved", p=out))
        return out

    # ---- timeline -> unique frames
    start = max(0.0, o.start or 0.0)
    if o.end and o.end > start:
        end = o.end
    elif vdur > 0:
        end = vdur
    else:
        end = msgs[-1].show + 10.0
    nframes = max(1, int(round((end - start) * fps)))
    log(T("s_frames", a=fmt_time(start), b=fmt_time(end), n=nframes, fps=f"{fps:g}"))
    segs, prev, cnt = [], None, 0
    for n in range(nframes):
        k = tl.key(start + n / fps)
        if k == prev:
            cnt += 1
        else:
            if prev is not None:
                segs.append((prev, cnt))
            prev, cnt = k, 1
        if n % 20000 == 0:
            check()
    segs.append((prev, cnt))

    temp_root = o.temp_dir or os.path.join(work, "temp")
    os.makedirs(temp_root, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="chat_overlay_", dir=temp_root)
    free = shutil.disk_usage(tmp).free / 1e9
    log(T("temp", p=tmp, gb=free))
    try:
        uid, entries = {}, []
        for key, c in segs:
            i = uid.get(key)
            if i is None:
                i = uid[key] = len(uid)
            entries.append((i, c))
        keys = [None] * len(uid)
        for key, i in uid.items():
            keys[i] = key
        log(T("uniq", n=len(keys)))
        render_unique_frames(keys, tmp, comp, (o, ch, box_h, cache_dir, work), prog, cancel, log)
        check()
        frame_map = [i for i, c in entries for _ in range(c)][:nframes]
        pngs = os.path.join(tmp, "f%06d.png")
        out = out_path
        log(T("out_path", p=out))
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        base = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
        full = o.canvas == "full"
        W, H = (cw, ch) if full else (bw, box_h)
        X, Y = (bx, by) if full else (0, 0)
        dur = end - start
        pad = f",pad={cw}:{ch}:{bx}:{by}:color=black@0" if full else ""
        log(T("smart", u=len(keys), n=nframes, x=nframes / max(1, len(keys))))

        def encode_unique(codec_args, path):
            """Nén mỗi khung KHÁC NHAU đúng 1 lần (chuỗi ảnh, đúng FPS), rồi dựng lại bảng mẫu MOV để đủ
            từng khung theo thứ tự – khung trùng trỏ chung dữ liệu. Thời gian chính xác tuyệt đối."""
            cmd = base + ["-framerate", _rate(fps), "-start_number", "0", "-i", pngs] + codec_args + ["-f", "mov", path]
            run_ffmpeg(cmd, len(keys) / fps, prog, cancel, log)
            check()
            log(T("assemble"))
            prog("assemble", 0.0)
            assemble_shared_mov(path, frame_map)

        if o.fmt in ("prores", "ffv1") and o.share_frames:
            codec = PRORES_ARGS if o.fmt == "prores" else FFV1_ARGS
            log(T("s_encode"))
            partial = out + ".partial.mov"
            try:
                encode_unique(["-vf", "format=rgba" + pad] + codec, partial)   # pad: viền trong suốt (cả khung hình)
                os.replace(partial, out)
            finally:
                if os.path.exists(partial):
                    os.remove(partial)
        else:
            # Mọi định dạng khác: dựng 1 file trung gian lossless, đủ khung, đúng thời gian, rồi chuyển đổi
            inter = os.path.join(tmp, "timeline.mov")
            log(T("s_encode"))
            encode_unique(["-vf", "format=rgba"] + FFV1_ARGS, inter)
            src = ["-i", inter]
            if o.fmt in ("mov", "webm", "prores", "ffv1"):
                cmd = base + src + ["-vf", "format=rgba" + pad]
                if o.fmt == "prores":
                    cmd += PRORES_ARGS
                elif o.fmt == "ffv1":
                    cmd += FFV1_ARGS
                elif o.fmt == "mov":      # QuickTime Animation
                    cmd += ["-c:v", "qtrle", "-pix_fmt", "argb", "-g", str(int(round(fps * 10)))]
                else:
                    cmd += ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-crf", "30", "-b:v", "0",
                            "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1", "-auto-alt-ref", "0"]
                cmd += [out]
            elif o.fmt == "green":
                enc = pick_encoder(ffmpeg, o.encoder, log)
                log(T("encoder", e=enc))
                cmd = base + src + ["-f", "lavfi", "-i", f"color=c=0x00FF00:s={W}x{H}:r={_rate(fps)}",
                                    "-filter_complex",
                                    f"[0:v]format=rgba[ov];[1:v][ov]overlay={X}:{Y}:shortest=1,format=yuv420p[v]",
                                    "-map", "[v]"] + encoder_args(enc) + ["-movflags", "+faststart", out]
            else:  # burn
                enc = pick_encoder(ffmpeg, o.encoder, log)
                log(T("encoder", e=enc) + (T("enc_cpu") if enc.startswith("lib") else "  (GPU)"))
                vin = ["-hwaccel", "auto"]
                vin += ["-ss", f"{start:.3f}"] if start > 0 else []
                vin += ["-t", f"{dur:.3f}", "-i", o.video]
                cmd = base + vin + src + ["-filter_complex",
                                          f"[1:v]format=rgba[ov];[0:v][ov]overlay={bx}:{by}:eof_action=pass,format=yuv420p[v]",
                                          "-map", "[v]", "-map", "0:a?"] + encoder_args(enc) + \
                    ["-c:a", "copy", "-movflags", "+faststart", out]
            run_ffmpeg(cmd, dur, prog, cancel, log)
    finally:
        if not os.environ.get("CHAT_OVERLAY_KEEP_TMP"):
            shutil.rmtree(tmp, ignore_errors=True)
    mb = os.path.getsize(out) / 1e6
    log(T("done", p=out, mb=mb, s=time.time() - t_begin))
    if start > 0:
        log(T("start_note", t=fmt_time(start)))
    return out


# ----------------------------------------------------------------------------- GUI
# (code, Tiếng Việt, English)
FMT_OPTS = [
    ("prores", "MOV trong suốt ProRes 4444 XQ – khuyên dùng cho DaVinci (nét nhất, chắc chắn đọc được)",
     "Transparent MOV, ProRes 4444 XQ – recommended for DaVinci (sharpest, universally supported)"),
    ("ffv1", "MOV trong suốt FFV1 lossless – DaVinci, file nhẹ hơn ProRes (nên thử trước)",
     "Transparent MOV, FFV1 lossless – DaVinci, smaller than ProRes (test it first)"),
    ("mov", "MOV trong suốt (Animation) – Premiere, After Effects, Final Cut",
     "Transparent MOV (Animation) – Premiere, After Effects, Final Cut"),
    ("webm", "WebM trong suốt (VP9) – OBS / trình duyệt", "Transparent WebM (VP9) – OBS / browsers"),
    ("green", "MP4 phông xanh – dùng Chroma Key (có GPU)", "Green-screen MP4 – chroma key (GPU encoding)"),
    ("burn", "Ghép thẳng vào video gốc (MP4, có GPU)", "Burn into the source video (MP4, GPU encoding)"),
]
STYLE_OPTS = [("text", "Chỉ chữ (viền đen, nền trong suốt)", "Text only (black outline, no background)"),
              ("bubble", "Bong bóng mờ từng tin", "Translucent bubble per message"),
              ("box", "Khung nền mờ kiểu YouTube", "YouTube-style translucent panel")]
POS_OPTS = [("bottom-left", "Dưới - trái", "Bottom left"), ("bottom-right", "Dưới - phải", "Bottom right"),
            ("left", "Giữa - trái", "Middle left"), ("right", "Giữa - phải", "Middle right"),
            ("top-left", "Trên - trái", "Top left"), ("top-right", "Trên - phải", "Top right")]
ENC_OPTS = [("auto", "Tự động (ưu tiên GPU)", "Auto (prefer GPU)"),
            ("av1_nvenc", "NVIDIA – AV1 (RTX 40/50)", "NVIDIA – AV1 (RTX 40/50)"),
            ("hevc_nvenc", "NVIDIA – HEVC (H.265)", "NVIDIA – HEVC (H.265)"),
            ("av1_qsv", "Intel – AV1 (Arc, Core Ultra)", "Intel – AV1 (Arc, Core Ultra)"),
            ("hevc_qsv", "Intel – HEVC (H.265)", "Intel – HEVC (H.265)"),
            ("hevc_amf", "AMD – HEVC (H.265)", "AMD – HEVC (H.265)"),
            ("hevc_videotoolbox", "Mac – HEVC (H.265)", "Mac – HEVC (H.265)"),
            ("libx264", "CPU – H.264 (chậm)", "CPU – H.264 (slow)"),
            ("libsvtav1", "CPU – AV1 SVT (rất chậm)", "CPU – AV1 SVT (very slow)")]
MAXH_OPTS = [("0", "Cao nhất có thể", "Highest available"), ("2160", "2160p (4K)", "2160p (4K)"),
             ("1440", "1440p (2K)", "1440p (2K)"), ("1080", "1080p", "1080p"), ("720", "720p", "720p"),
             ("480", "480p", "480p")]
VKIND_OPTS = [("both", "Hình + tiếng (ghép lại)", "Video + audio (merged)"),
              ("video", "Chỉ hình", "Video only"),
              ("audio", "Chỉ tiếng (m4a gốc, không đổi mã)", "Audio only (original m4a, not re-encoded)")]
OPT_LISTS = {"fmt": FMT_OPTS, "style": STYLE_OPTS, "position": POS_OPTS, "encoder": ENC_OPTS, "maxh": MAXH_OPTS,
             "vkind": VKIND_OPTS}
# (key, Tiếng Việt, English, mặc định/default, lưu lại giữa các lần mở/persist)
NUM_FIELDS = [
    ("max_messages", "Số tin tối đa", "Max messages on screen", "10", True),
    ("font_size", "Cỡ chữ (px @1080p)", "Font size (px @1080p)", "22", True),
    ("box_width", "Rộng khung (px @1080p)", "Box width (px @1080p)", "440", True),
    ("box_height", "Cao khung (px @1080p, 0=tự động)", "Box height (px @1080p, 0=auto)", "0", True),
    ("min_gap", "Giãn cách tối thiểu (s)", "Min gap between messages (s)", "0.1", True),
    ("anim", "Hiệu ứng trượt (s, 0=tắt)", "Slide animation (s, 0=off)", "0.12", True),
    ("max_lines", "Số dòng tối đa / tin", "Max lines per message", "4", True),
    ("hide_after", "Tự ẩn tin sau (s, 0=không)", "Hide messages after (s, 0=never)", "0", True),
    ("frame_size", "Khung hình (trống = theo video)", "Frame size (blank = from video)", "", True),
    ("fps", "FPS (trống = theo video)", "FPS (blank = from video)", "", True),
    ("offset", "Dời thời gian (s)", "Time offset (s)", "0", False),
    ("start", "Bắt đầu (vd 1:02:00)", "Start (e.g. 1:02:00)", "0", False),
    ("end", "Kết thúc (trống = hết)", "End (blank = to the end)", "", False),
]


def _opt_label(key, code):
    for c, vi, en in OPT_LISTS[key]:
        if c == code:
            return vi if LANG == "vi" else en
    return OPT_LISTS[key][0][1 if LANG == "vi" else 2]


def _opt_code(key, label):
    for c, vi, en in OPT_LISTS[key]:
        if label in (vi, en):
            return c
    return OPT_LISTS[key][0][0]


def open_path(p):
    try:
        if os.name == "nt":
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception:
        pass


def _set_window_icon(root, tk):
    """Logo cửa sổ: assets/icon.ico (bản .exe: nằm trong thư mục _internal). / Window icon from assets/."""
    base = getattr(sys, "_MEIPASS", SCRIPT_DIR)
    ico, png = os.path.join(base, "assets", "icon.ico"), os.path.join(base, "assets", "icon.png")
    try:
        if os.name == "nt" and os.path.isfile(ico):
            root.iconbitmap(default=ico)
        elif os.path.isfile(png):
            img = Image.open(png).convert("RGBA")
            photos = []
            for s in (64, 32, 16):
                small = img.resize((s, s), RESAMPLE)
                photos.append(tk.PhotoImage(width=s, height=s, data=_png_bytes(small), format="png"))
            root.iconphoto(True, *photos)
            root._icon_refs = photos      # giữ tham chiếu để Tk không xoá ảnh / keep refs alive
    except Exception:
        pass


def _png_bytes(im):
    import base64
    import io
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue())


def launch_gui():
    try:
        import queue
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        print(T("no_tk"))
        return

    st = load_settings()
    set_lang(st.get("lang") or detect_lang())
    register_native_host()   # tự đăng ký lại mỗi lần mở, tự sửa nếu đã di chuyển thư mục app
    if os.name == "nt":      # taskbar hiện logo của app thay vì logo Python / own taskbar icon instead of Python's
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ChatOverlay.YouTubeLiveChat")
        except Exception:
            pass
    root = tk.Tk()
    root.title(APP_TITLE)
    root.minsize(780, 720)
    _set_window_icon(root, tk)
    q = queue.Queue()
    cancel_ev = threading.Event()
    busy = [False]
    W = {}
    log_lines = []

    def SV(v=""):
        return tk.StringVar(value=v)

    paths = {k: SV() for k in ("url", "chat", "video", "output")}
    paths["work"] = SV(st.get("work_dir", ""))
    try:
        prepare_work_dir(paths["work"].get())     # file tạm của cả giao diện cũng vào thư mục làm việc
    except RuntimeError:
        pass
    paths["dldir"] = SV(st.get("download_dir", ""))
    paths["viddir"] = SV(st.get("video_dir", ""))
    vurl = SV()                         # tab Tải video: giữ ngoài build() để không mất khi đổi ngôn ngữ
    v_delsrc = tk.BooleanVar(value=bool(st.get("video_del_src", False)))
    tab_idx = [0]
    win_fixed = [False]
    ytver = SV("")
    yt_checked = [float(st.get("ytdlp_checked", 0) or 0)]
    nums = {k: SV(str(st.get(k, d)) if keep else d) for k, _, _, d, keep in NUM_FIELDS}
    codes = {}
    for key, default in (("fmt", "prores"), ("style", "text"), ("position", "bottom-left"), ("encoder", "auto"),
                         ("maxh", "0"), ("vkind", "both")):
        val = st.get(key, default)
        codes[key] = val if any(c == val for c, _, _ in OPT_LISTS[key]) else default
    v_av = tk.BooleanVar(value=bool(st.get("avatars", True)))
    v_canvas = tk.BooleanVar(value=bool(st.get("box_only", True)))
    v_share = tk.BooleanVar(value=bool(st.get("share_frames", True)))
    v_prev = SV(st.get("preview_at", "5:00"))
    v_browser = SV(st.get("cookie_browser", "chrome"))
    status = SV("")

    def save():
        d = {"lang": LANG, "work_dir": paths["work"].get().strip(), "download_dir": paths["dldir"].get().strip(),
             "avatars": v_av.get(),
             "box_only": v_canvas.get(), "share_frames": v_share.get(), "preview_at": v_prev.get(),
             "cookie_browser": v_browser.get(), "video_dir": paths["viddir"].get().strip(),
             "video_del_src": v_delsrc.get(), "ytdlp_checked": yt_checked[0]}
        d.update(codes)
        for k, _, _, _, keep in NUM_FIELDS:
            if keep:
                d[k] = nums[k].get().strip()
        save_settings(d)

    def add_log(s):
        log_lines.append(s)
        del log_lines[:-500]
        if "txt" in W:
            W["txt"].insert("end", s + "\n")
            W["txt"].see("end")

    def set_busy(flag):
        busy[0] = flag
        for b in W.get("actions", []):
            b.config(state="disabled" if flag else "normal")
        for b in W.get("cancels", []):
            b.config(state="normal" if flag else "disabled")
        if "lang" in W:
            W["lang"].config(state="disabled" if flag else "readonly")

    def build():
        for w in root.winfo_children():
            w.destroy()
        W.clear()
        outer = ttk.Frame(root, padding=12)
        outer.pack(fill="both", expand=True)
        top = ttk.Frame(outer)
        top.pack(fill="x")
        bot = ttk.Frame(outer)                     # trạng thái + thanh tiến độ + log dùng chung cho 2 tab / shared by both tabs
        bot.pack(side="bottom", fill="both", expand=True)
        nb = ttk.Notebook(outer)
        nb.pack(side="top", fill="x", pady=(4, 0))
        frm = ttk.Frame(nb, padding=(4, 8))
        frm.columnconfigure(1, weight=1)
        nb.add(frm, text=T("g_tab_chat"))
        vfrm = ttk.Frame(nb, padding=(4, 8))
        vfrm.columnconfigure(1, weight=1)
        nb.add(vfrm, text=T("g_tab_video"))
        W["nb"] = nb
        nb.select(tab_idx[0])
        def fit_tab(_e=None):
            """Tab Tải video thấp hơn tab Khung chat: thu notebook lại để ô log phía dưới to ra.
            The video tab is shorter than the chat tab: shrink the notebook so the log below gets the spare room."""
            tab_idx[0] = nb.index(nb.select())
            root.update_idletasks()
            if not win_fixed[0]:
                root.geometry(f"{root.winfo_width()}x{root.winfo_height()}")   # giữ cỡ cửa sổ / keep the window size
                win_fixed[0] = True
            nb.configure(height=nb.nametowidget(nb.select()).winfo_reqheight())
        nb.bind("<<NotebookTabChanged>>", fit_tab)
        P = dict(padx=5, pady=3)
        r = 0

        lang_var = SV(LANG_NAMES[LANG])
        cb = ttk.Combobox(top, textvariable=lang_var, values=list(LANG_NAMES.values()), state="readonly", width=12)
        cb.pack(side="right")
        ttk.Label(top, text="Ngôn ngữ / Language").pack(side="right", padx=6)
        W["lang"] = cb

        def on_lang(_e=None):
            new = {v: k for k, v in LANG_NAMES.items()}[lang_var.get()]
            if new != LANG:
                set_lang(new)
                save()
                build()
        cb.bind("<<ComboboxSelected>>", on_lang)

        def file_row(label, key, kind):
            nonlocal r
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", **P)
            ttk.Entry(frm, textvariable=paths[key]).grid(row=r, column=1, sticky="ew", **P)

            def browse():
                if kind == "chat":
                    p = filedialog.askopenfilename(filetypes=[("Live chat JSON", "*.json"), ("*", "*.*")])
                elif kind == "video":
                    p = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mkv *.webm *.mov"), ("*", "*.*")])
                elif kind == "dir":
                    p = filedialog.askdirectory(initialdir=paths[key].get().strip() or None)
                else:
                    p = filedialog.asksaveasfilename()
                if p:
                    paths[key].set(p)
                    save()
            ttk.Button(frm, text=T("g_browse"), command=browse).grid(row=r, column=2, sticky="ew", **P)
            r += 1

        ttk.Label(frm, text=T("g_url")).grid(row=r, column=0, sticky="w", **P)
        ttk.Entry(frm, textvariable=paths["url"]).grid(row=r, column=1, sticky="ew", **P)
        b_dl = ttk.Button(frm, text=T("g_dl"), command=start_download)
        b_dl.grid(row=r, column=2, sticky="ew", **P)
        r += 1
        ttk.Label(frm, text=T("g_browser")).grid(row=r, column=0, sticky="w", **P)
        ttk.Combobox(frm, textvariable=v_browser, values=BROWSERS, state="readonly", width=10).grid(
            row=r, column=1, sticky="w", **P)
        b_ck = ttk.Button(frm, text=T("g_ck_btn"), command=start_export_cookies)
        b_ck.grid(row=r, column=2, sticky="ew", **P)
        r += 1
        file_row(T("g_dldir"), "dldir", "dir")
        file_row(T("g_chat"), "chat", "chat")
        file_row(T("g_video"), "video", "video")
        file_row(T("g_out"), "output", "out")
        file_row(T("g_work"), "work", "dir")

        for key, lab in (("fmt", "g_fmt"), ("style", "g_style"), ("position", "g_pos"), ("encoder", "g_enc")):
            ttk.Label(frm, text=T(lab)).grid(row=r, column=0, sticky="w", **P)
            var = SV(_opt_label(key, codes[key]))
            c = ttk.Combobox(frm, textvariable=var, state="readonly",
                             values=[_opt_label(key, code) for code, _, _ in OPT_LISTS[key]])
            c.grid(row=r, column=1, columnspan=2, sticky="ew", **P)
            c.bind("<<ComboboxSelected>>", lambda e, k=key, v=var: codes.__setitem__(k, _opt_code(k, v.get())))
            r += 1

        grid = ttk.Frame(frm)
        grid.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(6, 2))
        r += 1
        for i, (key, vi, en, _, _) in enumerate(NUM_FIELDS):
            rr, cc = divmod(i, 2)
            ttk.Label(grid, text=vi if LANG == "vi" else en).grid(row=rr, column=cc * 2, sticky="w", padx=5, pady=2)
            ttk.Entry(grid, textvariable=nums[key], width=11).grid(row=rr, column=cc * 2 + 1, sticky="w", padx=5, pady=2)

        ttk.Checkbutton(frm, text=T("g_avatars"), variable=v_av).grid(row=r, column=0, columnspan=3, sticky="w", **P)
        r += 1
        ttk.Checkbutton(frm, text=T("g_canvas"), variable=v_canvas).grid(row=r, column=0, columnspan=3, sticky="w", **P)
        r += 1
        ttk.Checkbutton(frm, text=T("g_share"), variable=v_share).grid(row=r, column=0, columnspan=3, sticky="w", **P)
        r += 1

        bar = ttk.Frame(frm)
        bar.grid(row=r, column=0, columnspan=3, sticky="ew", pady=6)
        r += 1
        ttk.Label(bar, text=T("g_prev_at")).pack(side="left")
        ttk.Entry(bar, textvariable=v_prev, width=9).pack(side="left", padx=4)
        b_prev = ttk.Button(bar, text=T("g_prev"), command=lambda: start(True))
        b_prev.pack(side="left", padx=4)
        b_run = ttk.Button(bar, text=T("g_run"), command=lambda: start(False))
        b_run.pack(side="left", padx=4)
        b_cancel = ttk.Button(bar, text=T("g_cancel"), command=cancel_ev.set)
        b_cancel.pack(side="left", padx=4)

        # ---- tab "Tải video" / "Download video" tab
        vr = 0
        ttk.Label(vfrm, text=T("gv_hint"), wraplength=700, justify="left").grid(
            row=vr, column=0, columnspan=3, sticky="w", **P)
        vr += 1
        ttk.Label(vfrm, text=T("g_url")).grid(row=vr, column=0, sticky="w", **P)
        ttk.Entry(vfrm, textvariable=vurl).grid(row=vr, column=1, sticky="ew", **P)
        vbtn = ttk.Frame(vfrm)
        vbtn.grid(row=vr, column=2, sticky="ew", **P)
        b_vchk = ttk.Button(vbtn, text=T("gv_check"), command=lambda: start_video(check=True))
        b_vchk.pack(side="left", fill="x", expand=True)
        b_vdl = ttk.Button(vbtn, text=T("gv_go"), command=start_video)
        b_vdl.pack(side="left", fill="x", expand=True, padx=(4, 0))
        vr += 1
        ttk.Label(vfrm, text=T("gv_dir")).grid(row=vr, column=0, sticky="w", **P)
        ttk.Entry(vfrm, textvariable=paths["viddir"]).grid(row=vr, column=1, sticky="ew", **P)

        def browse_vdir():
            p = filedialog.askdirectory(initialdir=paths["viddir"].get().strip() or None)
            if p:
                paths["viddir"].set(p)
                save()
        ttk.Button(vfrm, text=T("g_browse"), command=browse_vdir).grid(row=vr, column=2, sticky="ew", **P)
        vr += 1
        ttk.Label(vfrm, text=T("gv_kind")).grid(row=vr, column=0, sticky="w", **P)
        kd_var = SV(_opt_label("vkind", codes["vkind"]))
        kd = ttk.Combobox(vfrm, textvariable=kd_var, state="readonly", width=40,
                          values=[_opt_label("vkind", code) for code, _, _ in OPT_LISTS["vkind"]])
        kd.grid(row=vr, column=1, sticky="w", **P)
        kd.bind("<<ComboboxSelected>>", lambda e: codes.__setitem__("vkind", _opt_code("vkind", kd_var.get())))
        vr += 1
        ttk.Label(vfrm, text=T("gv_maxh")).grid(row=vr, column=0, sticky="w", **P)
        mh_var = SV(_opt_label("maxh", codes["maxh"]))
        mh = ttk.Combobox(vfrm, textvariable=mh_var, state="readonly", width=24,
                          values=[_opt_label("maxh", code) for code, _, _ in OPT_LISTS["maxh"]])
        mh.grid(row=vr, column=1, sticky="w", **P)
        mh.bind("<<ComboboxSelected>>", lambda e: codes.__setitem__("maxh", _opt_code("maxh", mh_var.get())))
        vr += 1
        ttk.Checkbutton(vfrm, text=T("gv_del"), variable=v_delsrc).grid(row=vr, column=0, columnspan=3, sticky="w", **P)
        vr += 1
        b_vcancel = ttk.Button(vfrm, text=T("g_cancel"), command=cancel_ev.set)
        b_vcancel.grid(row=vr, column=2, sticky="ew", **P)

        vr += 1
        ttk.Label(vfrm, textvariable=ytver).grid(row=vr, column=0, columnspan=2, sticky="w", **P)
        ttk.Button(vfrm, text=T("gv_upd"), command=lambda: start_ytdlp_check(True)).grid(
            row=vr, column=2, sticky="ew", **P)
        W["actions"] = [b_dl, b_prev, b_run, b_vchk, b_vdl]
        W["cancels"] = [b_cancel, b_vcancel]

        if not status.get() or not busy[0]:
            status.set(T("g_ready"))
        ttk.Label(bot, textvariable=status).pack(fill="x", **P)
        pb = ttk.Progressbar(bot, maximum=1000)
        pb.pack(fill="x", **P)
        W["pb"] = pb
        txt = tk.Text(bot, height=7, wrap="word")
        txt.pack(fill="both", expand=True, **P)
        txt.insert("end", "\n".join(log_lines) + ("\n" if log_lines else ""))
        W["txt"] = txt
        set_busy(busy[0])
        root.after(50, fit_tab)

    def collect():
        o = Options()
        o.chat, o.video, o.output = paths["chat"].get().strip(), paths["video"].get().strip(), paths["output"].get().strip()
        o.work_dir = paths["work"].get().strip()
        o.fmt, o.style, o.position, o.encoder = codes["fmt"], codes["style"], codes["position"], codes["encoder"]
        o.avatars, o.canvas = v_av.get(), ("box" if v_canvas.get() else "full")
        o.share_frames = v_share.get()
        field = ""
        try:
            field = "max_messages"; o.max_messages = max(1, int(nums[field].get()))
            field = "font_size"; o.font_size = int(nums[field].get())
            field = "box_width"; o.box_width = int(nums[field].get())
            field = "box_height"; o.box_height = int(nums[field].get() or 0)
            field = "min_gap"; o.min_gap = float(nums[field].get())
            field = "anim"; o.anim = max(0.0, float(nums[field].get() or 0))
            field = "max_lines"; o.max_lines = int(nums[field].get() or 4)
            field = "hide_after"; o.hide_after = float(nums[field].get() or 0)
            field = "offset"; o.offset = float(nums[field].get() or 0)
            field = "start"; o.start = parse_time(nums[field].get()) or 0.0
            field = "end"; o.end = parse_time(nums[field].get()) or 0.0
            field = "fps"; o.fps = float(nums[field].get() or 0)
            field = "frame_size"
            fs = nums[field].get().strip().lower().replace("×", "x")
            if fs:
                o.width, o.height = (int(v) for v in fs.split("x"))
        except ValueError:
            label = next((vi if LANG == "vi" else en) for k, vi, en, _, _ in NUM_FIELDS if k == field)
            messagebox.showerror(APP_TITLE, T("g_err_num", f=label))
            return None
        if not os.path.isfile(o.chat):
            messagebox.showerror(APP_TITLE, T("g_err_chat"))
            return None
        if o.fmt == "burn" and not os.path.isfile(o.video):
            messagebox.showerror(APP_TITLE, T("g_err_burn"))
            return None
        return o

    def begin():
        cancel_ev.clear()
        set_busy(True)
        W["pb"].config(mode="determinate")
        W["pb"]["value"] = 0
        save()

    def start(preview):
        o = collect()
        if not o:
            return
        if preview:
            try:
                o.preview_at = parse_time(v_prev.get()) or 0.0
            except ValueError:
                messagebox.showerror(APP_TITLE, T("g_err_prev"))
                return
        begin()
        log_lines.clear()
        W["txt"].delete("1.0", "end")
        launch(o, preview)

    def launch(o, preview):
        def work():
            try:
                out = run(o, log=lambda s: q.put(("log", s)), progress=lambda ph, f: q.put(("prog", ph, f)),
                          cancel=cancel_ev)
                q.put(("done", out, preview))
            except Cancelled:
                q.put(("cancel",))
            except PairMismatch as e:       # hỏi người dùng thay vì báo lỗi / ask instead of failing
                q.put(("mismatch", str(e), o, preview))
            except Exception as e:
                q.put(("log", traceback.format_exc()))
                q.put(("err", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def start_download():
        url = paths["url"].get().strip()
        if not re.match(r"https?://", url):
            messagebox.showerror(APP_TITLE, T("g_err_url"))
            return
        vid = paths["video"].get().strip()
        chosen = os.path.expanduser(paths["dldir"].get().strip())
        if chosen:                       # thư mục người dùng chọn (được ghi nhớ) / user-chosen, remembered
            out_dir = chosen
        elif vid and os.path.isfile(vid):
            out_dir = os.path.dirname(os.path.abspath(vid))
        else:
            out_dir = default_download_dir()
        begin()
        W["pb"].config(mode="indeterminate")
        W["pb"].start(15)

        def work():
            try:
                p = download_chat(url, out_dir, log=lambda s: q.put(("log", s)),
                                  progress=lambda ph, f: q.put(("prog", ph, f)), cancel=cancel_ev,
                                  work_dir=paths["work"].get().strip())
                q.put(("chat_ready", p))
            except Cancelled:
                q.put(("cancel",))
            except Exception as e:
                q.put(("log", traceback.format_exc()))
                q.put(("err", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def start_video(check=False):
        url = vurl.get().strip()
        if not re.match(r"https?://", url):
            messagebox.showerror(APP_TITLE, T("g_err_url"))
            return
        out_dir = os.path.expanduser(paths["viddir"].get().strip()) or default_download_dir()
        max_h, del_src, work_dir = int(codes["maxh"]), v_delsrc.get(), paths["work"].get().strip()
        kind = codes["vkind"]
        begin()
        log_lines.clear()
        W["txt"].delete("1.0", "end")
        W["pb"].config(mode="indeterminate")
        W["pb"].start(15)

        def work():
            try:
                p = download_video(url, out_dir, max_h, del_src, log=lambda s: q.put(("log", s)),
                                   progress=lambda ph, f: q.put(("prog", ph, f)), cancel=cancel_ev, work_dir=work_dir,
                                   kind=kind, list_only=check)
                q.put(("formats_ready" if check else "video_ready", p))
            except Cancelled:
                q.put(("cancel",))
            except Exception as e:
                q.put(("log", traceback.format_exc()))
                q.put(("err", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def start_ytdlp_check(manual):
        if manual:
            add_log(T("yu_checking"))

        def work():
            try:
                cur = ytdlp_current_version()
                q.put(("ytver", cur))
                q.put(("ytdlp_info", cur, ytdlp_latest_version(), manual))
            except Exception as e:
                q.put(("ytdlp_err", str(e), manual))
        threading.Thread(target=work, daemon=True).start()

    def start_ytdlp_update(tag):
        add_log(T("yu_getting", v=tag))

        def work():
            try:
                ytdlp_download_update(tag)
                q.put(("ytdlp_done", tag))
            except Exception as e:
                q.put(("ytdlp_err", str(e), True))
        threading.Thread(target=work, daemon=True).start()

    def start_export_cookies():
        browser = v_browser.get().strip() or "chrome"
        dest_dir = (os.path.expanduser(paths["dldir"].get().strip()) or
                    os.path.expanduser(paths["work"].get().strip()) or default_download_dir())
        dest = os.path.join(dest_dir, "cookies.txt")
        save()
        begin()
        W["pb"].config(mode="indeterminate")
        W["pb"].start(15)

        def work():
            try:
                ext = try_extension_export()
                if ext:
                    text, n = ext
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "w", encoding="utf-8", newline="\n") as f:
                        f.write(text)
                    q.put(("log", T("ck_ext_done", n=n, p=dest)))
                    q.put(("cookies_ready", dest))
                    return
                p = export_cookies_from_browser(browser, dest, log=lambda s: q.put(("log", s)))
                q.put(("cookies_ready", p))
            except Exception as e:
                q.put(("log", traceback.format_exc()))
                q.put(("err", T("ck_fail", e=str(e))))
        threading.Thread(target=work, daemon=True).start()

    def finish():
        set_busy(False)
        pb = W["pb"]
        pb.stop()
        pb.config(mode="determinate")

    def poll():
        try:
            while True:
                it = q.get_nowait()
                kind = it[0]
                if kind == "log":
                    add_log(it[1])
                elif kind == "prog":
                    ph, f = it[1], it[2]
                    if ph == "chat":
                        status.set(T("ph_chat", mb=f / 1e6))
                    elif f < 0:                  # không biết % (đọc danh sách, ghép) / unknown % (listing, merging)
                        status.set(T("ph_" + ph) + "…")
                        if str(W["pb"].cget("mode")) != "indeterminate":
                            W["pb"].config(mode="indeterminate")
                            W["pb"].start(15)
                    else:
                        if str(W["pb"].cget("mode")) != "determinate":
                            W["pb"].stop()
                            W["pb"].config(mode="determinate")
                        status.set(f"{T('ph_' + ph)}… {f * 100:.0f}%")
                        W["pb"]["value"] = f * 1000
                elif kind == "ytver":
                    ytver.set(T("gv_ytver", v=it[1] + (" ✔" if YTDLP_OVERRIDE else "")))
                elif kind == "ytdlp_info":
                    cur, new, manual = it[1], it[2], it[3]
                    if _vkey(new) > _vkey(cur):
                        if (manual or time.time() - yt_checked[0] > UPDATE_DAYS * 86400) and messagebox.askyesno(
                                APP_TITLE, T("yu_new", new=new, cur=cur)):
                            start_ytdlp_update(new)
                    elif manual:
                        add_log(T("yu_latest", cur=cur))
                        messagebox.showinfo(APP_TITLE, T("yu_latest", cur=cur))
                    if manual or time.time() - yt_checked[0] > UPDATE_DAYS * 86400:
                        yt_checked[0] = time.time()
                        save()
                elif kind == "ytdlp_done":
                    add_log(T("yu_done", v=it[1]))
                    messagebox.showinfo(APP_TITLE, T("yu_done", v=it[1]))
                elif kind == "ytdlp_err":
                    add_log(T("yu_fail", e=it[1][:300]))
                    if it[2]:
                        messagebox.showerror(APP_TITLE, T("yu_fail", e=it[1][:300]))
                elif kind == "formats_ready":
                    finish()
                    status.set(it[1])
                elif kind == "video_ready":
                    finish()
                    W["pb"]["value"] = 1000
                    status.set(T("gv_done", p=it[1]))
                    if messagebox.askyesno(APP_TITLE, T("gv_open", p=it[1])):
                        open_path(os.path.dirname(os.path.abspath(it[1])))
                elif kind == "chat_ready":
                    finish()
                    paths["chat"].set(it[1])
                    status.set(T("g_chat_ok", p=os.path.basename(it[1])))
                elif kind == "cookies_ready":
                    finish()
                    status.set(T("g_ck_ok", p=it[1]))
                elif kind == "done":
                    finish()
                    W["pb"]["value"] = 1000
                    status.set(T("g_done", p=it[1]))
                    if it[2]:
                        open_path(it[1])
                    elif messagebox.askyesno(APP_TITLE, T("g_open", p=it[1])):
                        open_path(os.path.dirname(os.path.abspath(it[1])))
                elif kind == "mismatch":
                    add_log(it[1])
                    if messagebox.askyesno(APP_TITLE, it[1] + "\n\n" + T("mm_ask"), icon="warning"):
                        it[2].check_pair = False
                        launch(it[2], it[3])
                    else:
                        finish()
                        status.set(T("cancelled"))
                elif kind == "cancel":
                    finish()
                    status.set(T("cancelled"))
                elif kind == "err":
                    finish()
                    status.set(T("g_err"))
                    messagebox.showerror(APP_TITLE, it[1][:800])
        except queue.Empty:
            pass
        root.after(100, poll)

    def on_close():
        save()
        cancel_ev.set()
        root.destroy()

    def report(exc, val, tb):
        add_log("".join(traceback.format_exception(exc, val, tb)))
        messagebox.showerror(APP_TITLE, str(val)[:800])

    root.report_callback_exception = report
    root.protocol("WM_DELETE_WINDOW", on_close)
    build()
    poll()
    start_ytdlp_check(False)       # luôn đọc số phiên bản; chỉ hỏi cập nhật nếu đã quá 30 ngày / always read the version; ask only after 30 days
    root.mainloop()


# ----------------------------------------------------------------------------- CLI
def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv == ["--gui"]:
        launch_gui()
        return
    st = load_settings()
    set_lang(st.get("lang") or detect_lang())
    ap = argparse.ArgumentParser(description=APP_TITLE)
    ap.add_argument("chat", help="yt-dlp .live_chat.json file, or a YouTube link (the chat is downloaded first)")
    ap.add_argument("-o", "--output", default="")
    ap.add_argument("--video", default="", help="source video: provides size/length/fps (required for --format burn)")
    ap.add_argument("--format", dest="fmt", default="prores", choices=["prores", "ffv1", "mov", "webm", "green", "burn"])
    ap.add_argument("--style", default="text", choices=["text", "bubble", "box"])
    ap.add_argument("--position", default="bottom-left",
                    choices=["bottom-left", "bottom-right", "left", "right", "top-left", "top-right"])
    ap.add_argument("--margin-x", type=int, default=Options.margin_x, help="left/right margin in px @1080p")
    ap.add_argument("--margin-y", type=int, default=Options.margin_y, help="top/bottom margin in px @1080p")
    ap.add_argument("--canvas", default="box", choices=["box", "full"],
                    help="box = only the chat-box area (default), full = whole video frame")
    ap.add_argument("--no-share", action="store_true",
                    help="ProRes/FFV1: encode every frame instead of sharing identical frames")
    ap.add_argument("--size", default="1920x1080", help="frame size when no --video is given")
    ap.add_argument("--fps", type=float, default=0.0, help="0 = same as --video (or 30)")
    ap.add_argument("--max-messages", type=int, default=10)
    ap.add_argument("--font-size", type=int, default=22)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--box-width", type=int, default=440)
    ap.add_argument("--box-height", type=int, default=0)
    ap.add_argument("--min-gap", type=float, default=0.10)
    ap.add_argument("--anim", type=float, default=0.12)
    ap.add_argument("--max-lag", type=float, default=1.0)
    ap.add_argument("--hide-after", type=float, default=0.0)
    ap.add_argument("--max-lines", type=int, default=4)
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--start", default="0")
    ap.add_argument("--end", default="")
    ap.add_argument("--no-avatars", action="store_true")
    ap.add_argument("--no-download", action="store_true", help="do not download avatars/emoji images")
    ap.add_argument("--font", default="")
    ap.add_argument("--font-bold", default="")
    ap.add_argument("--ffmpeg", default="")
    ap.add_argument("--work-dir", default="",
                    help="work folder for temp frames + caches (default: the one saved by the GUI, else ./work)")
    ap.add_argument("--cache-dir", default="", help="override the avatar/emoji cache folder")
    ap.add_argument("--temp-dir", default="", help="override the temp-frames folder (default: <work-dir>/temp)")
    ap.add_argument("--download-dir", default="",
                    help="where to save the chat when a YouTube link is given (default: the folder remembered by the GUI)")
    ap.add_argument("--encoder", default="auto", choices=["auto", "libsvtav1"] + ENCODER_ORDER,
                    help="encoder for --format burn/green (auto = prefer GPU)")
    ap.add_argument("--preview", default="", help="only save a PNG preview at this time (e.g. 25:30)")
    ap.add_argument("--lang", default="", choices=["", "vi", "en"], help="message language")
    ap.add_argument("--ignore-mismatch", action="store_true",
                    help="export even if the chat and the video look like different streams")
    a = ap.parse_args(argv)
    if a.lang:
        set_lang(a.lang)
    w, h = (int(x) for x in a.size.lower().split("x"))
    o = Options(chat=a.chat, output=a.output, video=a.video, fmt=a.fmt, style=a.style, position=a.position,
                margin_x=a.margin_x, margin_y=a.margin_y,
                canvas=a.canvas, share_frames=not a.no_share, width=w, height=h, fps=a.fps, max_messages=a.max_messages, font_size=a.font_size,
                scale=a.scale, box_width=a.box_width, box_height=a.box_height, min_gap=a.min_gap,
                anim=a.anim, max_lag=a.max_lag, hide_after=a.hide_after, max_lines=a.max_lines, offset=a.offset,
                start=parse_time(a.start) or 0.0, end=parse_time(a.end) or 0.0, avatars=not a.no_avatars,
                download=not a.no_download, font=a.font, font_bold=a.font_bold, ffmpeg=a.ffmpeg,
                cache_dir=a.cache_dir, temp_dir=a.temp_dir, encoder=a.encoder,
                work_dir=a.work_dir or st.get("work_dir", ""),
                preview_at=parse_time(a.preview) if a.preview else -1.0, check_pair=not a.ignore_mismatch)
    last = [0.0]

    def progress(ph, f):
        now = time.time()
        if ph == "chat":
            if now - last[0] > 0.5:
                last[0] = now
                sys.stdout.write("\r   " + T("ph_chat", mb=f / 1e6) + "   ")
                sys.stdout.flush()
            return
        if now - last[0] > 0.5 or f >= 1:
            last[0] = now
            sys.stdout.write(f"\r   {ph}: {f * 100:5.1f}%   ")
            sys.stdout.flush()
            if f >= 1:
                sys.stdout.write("\n")

    log = lambda s: print("\r" + s)
    try:
        if re.match(r"https?://", o.chat):
            folder = (a.download_dir or st.get("download_dir")
                      or (os.path.dirname(os.path.abspath(o.video)) if o.video else os.getcwd()))
            o.chat = download_chat(o.chat, folder, log=log, progress=progress, work_dir=o.work_dir)
        run(o, log=log, progress=progress)
    except Cancelled:
        print(T("cancelled"))
    except PairMismatch as e:
        print("\n" + T("error"), e, "\n" + T("mm_cli"))
        sys.exit(1)
    except RuntimeError as e:
        print("\n" + T("error"), e)
        sys.exit(1)


if __name__ == "__main__":
    # Chrome khởi chạy app ở chế độ native host bằng cách gọi thẳng "<path> chrome-extension://ID/ …":
    # bắt trước MỌI thứ khác (freeze_support, thay stdout/stderr) vì chế độ này cần stdin/stdout nhị phân
    # thật để nói chuyện với trình duyệt. Chrome launches the app in native-host mode by exec'ing
    # "<path> chrome-extension://ID/ …" directly: catch this before anything else (freeze_support,
    # swapping stdout/stderr), since this mode needs real binary stdin/stdout to talk to the browser.
    if len(sys.argv) > 1 and sys.argv[1].startswith("chrome-extension://"):
        run_native_host()
        sys.exit(0)
    import multiprocessing
    multiprocessing.freeze_support()     # bản .exe: tiến trình con dựng khung hình không mở thêm cửa sổ app
    for _name in ("stdout", "stderr"):   # bản .exe không có console -> sys.stdout là None
        if getattr(sys, _name) is None:
            setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))
    main()
