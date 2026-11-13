<p align="center"><img src="assets/icon.png" alt="YouTube Live Chat Overlay" width="96"></p>

<h1 align="center">YouTube Live Chat Overlay</h1>

<p align="center">
  <b>Biến live chat replay của YouTube thành video nền trong suốt, khớp từng khung hình, để đặt chồng lên video của bạn.</b><br>
  Tải được cả buổi live: AV1 nét nhất, hoặc VP9 đổi sẵn cho DaVinci Resolve và Premiere.
</p>

<p align="center">
  <a href="https://github.com/Friendzoner49/youtube-chat-overlay/releases/latest"><img alt="Bản mới nhất" src="https://img.shields.io/github/v/release/Friendzoner49/youtube-chat-overlay?label=release&color=2ea44f"></a>
  <a href="https://github.com/Friendzoner49/youtube-chat-overlay/releases"><img alt="Lượt tải" src="https://img.shields.io/github/downloads/Friendzoner49/youtube-chat-overlay/total?color=blue"></a>
  <img alt="Nền tảng" src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey">
  <a href="LICENSE"><img alt="Giấy phép MIT" src="https://img.shields.io/badge/license-MIT-yellow"></a>
</p>

<p align="center"><a href="README.md">English</a> · <b>Tiếng Việt</b></p>

<p align="center"><img src="docs/styles.png" alt="Ba giao diện chat: chỉ chữ, bong bóng, khung nền"></p>

## Tải về

Không cần cài Python. Giải nén rồi chạy.

| Nền tảng | Tải | Dung lượng | Ghi chú |
|---|---|---|---|
| **Windows** 10 / 11 (64-bit) | [**ChatOverlay-windows.zip**](https://github.com/Friendzoner49/youtube-chat-overlay/releases/latest/download/ChatOverlay-windows.zip) | ~23 MB | Giải nén, chạy `ChatOverlay.exe` |
| **macOS** (Apple Silicon) | [**ChatOverlay-macos.zip**](https://github.com/Friendzoner49/youtube-chat-overlay/releases/latest/download/ChatOverlay-macos.zip) | ~21 MB | Chưa ký: xem [lần đầu mở trên macOS](#lần-đầu-mở-trên-macos) |

Mọi bản phát hành và ghi chú thay đổi: [Releases](https://github.com/Friendzoner49/youtube-chat-overlay/releases). Các bản build do GitHub Actions tự tạo từ chính repo này.

**Bạn cần cài thêm [FFmpeg](https://ffmpeg.org/download.html)** (không đóng gói kèm):
Windows `winget install Gyan.FFmpeg` · macOS `brew install ffmpeg`. Hoặc đặt `ffmpeg.exe` và `ffprobe.exe` cạnh app.

Muốn chạy từ mã nguồn? Xem [Chạy từ mã nguồn](#chạy-từ-mã-nguồn).

## App làm được gì

**Khung chat**
- **Khớp thời gian chính xác đến từng khung hình**, dựa trên mốc thời gian YouTube lưu cho từng tin nhắn.
- **Tin nhắn hiện lần lượt**, cách nhau ít nhất 0,1 giây, kèm hiệu ứng trượt lên ngắn. Một đợt tin dồn được dàn đều quanh mốc thật thay vì chỉ đẩy lùi về sau, nên chat luôn lệch không quá khoảng 1 giây so với thực tế.
- **3 giao diện:** chỉ chữ có viền, bong bóng mờ, hoặc khung nền kiểu YouTube. Hỗ trợ avatar, emoji YouTube và emoji thường, badge chủ kênh / quản trị viên / hội viên / đã xác minh, Super Chat, Super Sticker, hội viên mới.
- **Chỉ xuất đúng vùng khung chat** ở độ phân giải gốc, nên file nhẹ và nét. Đặt clip vào một góc trên timeline.
- **File trong suốt nhỏ.** Mỗi khung hình khác nhau chỉ nén một lần, các khung trùng dùng chung dữ liệu trong file MOV: 90 giây ở 60 fps chỉ cần nén 761 khung thay vì 5.400.
- **Phát hiện chọn nhầm file** trước khi xuất (ngày phát, tên file, mã video, độ dài) và hỏi lại trước khi tiếp tục.
- **Chỉ xuất đoạn cần dùng** (Bắt đầu / Kết thúc); tên file ghi rõ đoạn thời gian.
- **Định dạng:** ProRes 4444, FFV1 lossless, QuickTime Animation, WebM VP9 (đều trong suốt); MP4 phông xanh; hoặc ghép thẳng chat vào video bằng GPU (NVIDIA, Intel, AMD, Apple).

**Tải video**
- Nút **Kiểm tra định dạng** (`yt-dlp --list-formats`): xem video đã tải được chưa, rất hữu ích với livestream vừa kết thúc mà YouTube chưa xử lý xong.
- Nút **Tải video**: chọn luồng tốt nhất, tải và ghép. Độ phân giải tối đa do bạn chọn.
- **Có bản Premium →** lấy bản đó rồi đổi sang H.264 (`_final.mp4`) như VP9, vì DaVinci thường không mở được file Premium gốc. Không tải được thì tự lấy bản thường.
- **Có AV1 →** tải AV1 nét nhất + tiếng AAC, ghép thành `.mp4`, giữ nguyên.
- **Không có AV1 →** tải VP9 nét nhất rồi đổi bằng FFmpeg (`h264_nvenc`, VBR 15 Mbit/s, AAC 320k) thành `_final.mp4`, DaVinci Resolve và Premiere đọc chắc chắn.
- **Chỉ hình / chỉ tiếng.** Chỉ tiếng lưu đúng **m4a (AAC)** gốc, không đổi mã.
- Có thanh tiến độ, nút Huỷ, và tải tiếp được khi bị đứt mạng.

**Ngoài ra:** tải chat thẳng từ link, giao diện song ngữ Việt / Anh, đầy đủ dòng lệnh, và **cập nhật yt-dlp** ngay trong app.

## Bắt đầu nhanh

1. **Lấy chat.** Mở app, dán link YouTube rồi bấm **Tải chat** (hoặc chọn file `.live_chat.json` có sẵn).
2. **Chọn video gốc** (nên làm; app chỉ đọc kích thước, FPS và độ dài).
3. **Chọn kiểu xuất, giao diện, vị trí**, nhập *Bắt đầu* / *Kết thúc* nếu cần, rồi bấm **Xem thử ảnh** và **Xuất video**.
4. **Đặt vào phần mềm dựng.** Log in sẵn giá trị Position cho DaVinci Resolve; xem [Đặt khung chat vào DaVinci Resolve](#đặt-khung-chat-vào-davinci-resolve).

### Quy trình gợi ý cho buổi live dài

Nếu bạn cắt highlight từ buổi live nhiều giờ, hãy xuất chat **riêng cho từng highlight**: đặt *Bắt đầu* và *Kết thúc* theo vị trí highlight trong buổi live gốc (vd `1:02:00` → `1:10:00`), xuất, rồi đặt file chat lên track phía trên clip tương ứng, bắt đầu cùng khung hình. Xuất cả buổi live nhiều giờ thành video trong suốt rất tốn dung lượng đĩa (xem [Nên chọn định dạng nào?](#nên-chọn-định-dạng-nào)).

## Tab Tải video

Dán link, chọn thư mục và (nếu muốn) độ phân giải tối đa, rồi bấm **Tải video**. Cần có FFmpeg.

**Kiểm tra định dạng** (nên bấm trước với livestream): in bảng `yt-dlp --list-formats` vào ô log, cho biết đang có AV1 / VP9 / H.264 / Premium độ phân giải bao nhiêu, nếu bấm Tải bây giờ sẽ được bản nào, và kết luận: đã có AV1 / chưa có AV1 / chưa có định dạng nào (buổi live vừa kết thúc, YouTube đang xử lý: đợi rồi kiểm tra lại) / đang live / chưa bắt đầu. Nút này không tải gì.

1. App đọc danh sách định dạng (cùng dữ liệu với `yt-dlp --list-formats`, hiện trong ô log).
   - Nếu có bản **Premium** nét bằng hoặc hơn bản thường, app lấy bản Premium rồi đổi thành `_final.mp4` đúng như VP9 (DaVinci thường không mở được file Premium gốc). Tải bản Premium bị từ chối thì app tự chuyển sang các bước dưới.
2. Nếu có **AV1**, app tải AV1 nét nhất (trong giới hạn bạn chọn) cùng tiếng AAC rồi ghép thành `.mp4`. Nếu YouTube có VP9 độ phân giải *cao hơn* AV1 thì dùng VP9 để không mất độ nét.
3. Nếu không có AV1, app tải **VP9** nét nhất rồi đổi thành `<tên>_final.mp4` (`h264_nvenc`, preset p7, VBR 15 Mbit/s, AAC 320k). Máy không có card NVIDIA thì tự đổi bằng CPU (`libx264`, chậm hơn nhiều). Tick *Xoá file VP9 gốc* nếu chỉ cần file `_final.mp4`.
4. Nếu đang tải bị đứt (VPN, mạng), bấm nút lần nữa: phần đã tải được giữ lại và tải tiếp.

Ô **Tải gì** cho phép chỉ lấy phần cần dùng: *Hình + tiếng* (mặc định), *Chỉ hình* hoặc *Chỉ tiếng*. Chỉ tiếng giữ đúng đường **m4a (AAC)** gốc, nên phần mềm dựng nạp thẳng được và chất lượng đúng như YouTube lưu. Video nào không có m4a thì lấy bản tiếng tốt nhất còn lại và ghi chú trong log. File có đuôi tên `_video` / `_audio` nên không đè lên file hình + tiếng đã tải.

Bản HDR được tránh khi có bản SDR; bản có DRM bị bỏ qua. Video giới hạn tuổi / dành cho hội viên dùng chung `cookies.txt` với phần tải chat.

### Giữ yt-dlp luôn mới

YouTube hay đổi nên app tự cập nhật được yt-dlp. Mỗi lần mở, nếu đã khoảng **1 tháng** chưa kiểm tra, app xem trên GitHub có yt-dlp mới không và hỏi trước khi làm gì; nút **Kiểm tra cập nhật yt-dlp** dùng được bất cứ lúc nào. File chính thức được tải từ bản phát hành của yt-dlp, đối chiếu mã SHA-256 của chính bản đó, rồi lưu vào thư mục `yt-dlp-update` cạnh `settings.json`. Mở lại app để dùng. Tab hiện phiên bản đang dùng (✔ = đang dùng bản đã cập nhật). Cách này giống nhau cho bản Windows, macOS và chạy từ mã nguồn.

## Video giới hạn tuổi và dành riêng cho hội viên

Cần cookies đăng nhập YouTube, lưu thành `cookies.txt` trong thư mục tải (app sẽ tự dùng):

- **Không cần đóng trình duyệt (Windows, khuyến nghị):** nạp tiện ích nhỏ [`browser-extension/`](browser-extension) 1 lần (`chrome://extensions` → Developer mode → Load unpacked; xem README của tiện ích). Từ đó nút **Lấy cookies** trong app nói chuyện thẳng với tiện ích qua kết nối cục bộ và tự lưu `cookies.txt`. Tiện ích đọc cookie qua API chính thức của trình duyệt, không đụng tới file cookie đang bị khoá.
- **Khi đã đóng trình duyệt:** chọn trình duyệt cạnh nút **Lấy cookies** rồi bấm. File cookie bị khoá khi trình duyệt đang chạy, nên phải đóng hẳn (kể cả tiến trình nền / khay hệ thống), nếu không sẽ báo "could not copy cookie database".

YouTube còn cần một chương trình chạy JavaScript để lấy danh sách định dạng video. Cài [Node.js](https://nodejs.org) (bản LTS) hoặc [Deno](https://deno.com); app tự tìm thấy. Nếu thiếu, việc tải có thể báo "This content is age-restricted" dù cookies vẫn đúng.

## Chi tiết cài đặt

### Lần đầu mở trên macOS

App chưa được ký, nên lần đầu mở cần thêm một bước:

```bash
xattr -dr com.apple.quarantine ChatOverlay.app     # gỡ cờ cách ly của Gatekeeper
```

Hoặc chuột phải `ChatOverlay.app` → **Open** → xác nhận (chỉ một lần). App mở từ Finder không có `PATH` của Terminal, nên FFmpeg cũng được tìm trong `/opt/homebrew/bin` và `/usr/local/bin`.

### Chạy từ mã nguồn

Yêu cầu: Python 3.8+, FFmpeg (`ffmpeg` và `ffprobe` trong `PATH`), và các thư viện trong `requirements.txt` ([Pillow](https://python-pillow.org/), [yt-dlp](https://github.com/yt-dlp/yt-dlp)).

```bash
pip install -r requirements.txt
python chat_overlay.py            # mở giao diện
```

- **Windows, không hiện cửa sổ đen:** bấm đúp **`ChatOverlay.pyw`**. Lần đầu app tự cài thư viện còn thiếu; không cần quyền admin.
- **macOS dùng Python của Homebrew:** giao diện cần Tk: `brew install python-tk`.

### Tự build

```bat
pip install -r requirements.txt pyinstaller
python build_exe.py
```

Windows: tạo thư mục `ChatOverlay\` (khoảng 43 MB) chứa `ChatOverlay.exe`; giữ cả thư mục cùng nhau. Cài đặt nằm trong `settings.json` cạnh file `.exe` và được giữ khi build lại; `build_exe.py` cũng cập nhật yt-dlp trước.

macOS:

```bash
pyinstaller --noconfirm --clean --windowed --name ChatOverlay --icon assets/icon.png \
  --exclude-module PIL._avif --add-data "assets:assets" chat_overlay.py
```

Kết quả là `dist/ChatOverlay.app`.

## Cách dùng: chi tiết

- **Tải chat** tương đương lệnh `yt-dlp --write-subs --sub-langs live_chat --skip-download URL`. Nếu ô **Thư mục lưu chat tải về** để trống, chat được lưu cạnh video gốc đã chọn, hoặc trong thư mục Downloads.
- **Cài đặt** (ngôn ngữ, thư mục, giao diện, định dạng, kích thước…) được ghi nhớ trong `settings.json` cạnh app, nên không ghi gì vào ổ hệ thống. Chỉ khi thư mục đó không ghi được, app mới dùng `%APPDATA%\ChatOverlay\` (Windows) hoặc `~/.config/ChatOverlay/`.

### Thư mục làm việc (file tạm + cache)

Mọi thứ app ghi ra trong lúc xử lý đều nằm trong một **thư mục làm việc**:

| Thư mục con | Nội dung |
|---|---|
| `temp/` | khung hình tạm (vài GB với chat dài, xoá sau mỗi lần xuất), cùng file tạm của Python, FFmpeg, yt-dlp |
| `cache/` | avatar, emoji, badge đã tải (dùng lại lần sau) |
| `yt-dlp-cache/` | cache nhỏ của yt-dlp |

Mặc định là `work/` cạnh app (trên macOS, bản `.app` dùng `~/Library/Application Support/ChatOverlay/work`). Để ổ hệ thống còn trống, hãy chọn thư mục trên ổ khác trong **Thư mục làm việc (file tạm + cache)**, ví dụ `D:\LivechatTemp`. App ghi nhớ lựa chọn này.

## Nên chọn định dạng nào?

| Kiểu xuất | Trong suốt | Dung lượng (vùng khung chat, 1080p 60 fps, chat đông, mỗi phút) | Phù hợp |
|---|---|---|---|
| **ProRes 4444 XQ** (`prores`, mặc định) | có | ~130 MB | **DaVinci Resolve** và mọi app khác; chắc chắn nhất |
| **FFV1 lossless** (`ffv1`) | có | ~50 MB | DaVinci Resolve (Blackmagic có liệt kê hỗ trợ FFV1 RGBA). Đúng từng điểm ảnh và nhẹ hơn; nên thử một lần trước |
| **QuickTime Animation** (`mov`) | có | ~100 MB | Premiere Pro, After Effects, Final Cut. DaVinci đọc được nhưng **mất** nền trong suốt |
| **WebM VP9** (`webm`) | có | ~6 MB | OBS, trình duyệt |
| **MP4 phông xanh** (`green`) | dùng chroma key | nhỏ | mọi app (mã hoá bằng GPU) |
| **Ghép thẳng** (`burn`) | — | ≈ video gốc | ra luôn video hoàn chỉnh (mã hoá bằng GPU) |

Dung lượng đo trên chat thật; lúc chat vắng gần như không tốn gì.

**Vì sao file trong suốt không dùng GPU:** bộ mã hoá GPU (NVENC, Quick Sync, AMF) chỉ xuất H.264 / HEVC / AV1 *không có* kênh trong suốt. Mọi định dạng trong suốt mà phần mềm dựng đọc được (ProRes 4444, FFV1, DNxHR 444) đều mã hoá bằng CPU. Để bù lại, app dựng khung hình trên mọi nhân CPU, chỉ nén mỗi khung khác nhau một lần, và chỉ xuất vùng khung chat. GPU được dùng cho phông xanh và ghép thẳng.

### Đặt khung chat vào DaVinci Resolve

Sau khi xuất, log in ra dạng:

```
DaVinci: Inspector → Retime and Scaling → Scaling = Crop (giữ nguyên kích thước, nét 1:1),
         rồi Transform → Position X = -700, Y = -67 (timeline 1920x1080) để đặt đúng vị trí đã chọn
```

1. Đặt file chat lên track phía trên clip, bắt đầu cùng khung hình.
2. Trong **Inspector**, đặt **Retime and Scaling → Scaling** = **Crop**. Nếu không, DaVinci sẽ phóng clip nhỏ lên và chữ bị mờ.
3. Nhập **Position X/Y** đã in ra vào mục **Transform**. Các giá trị này giả định timeline có cùng độ phân giải với video gốc.

Nếu phần mềm dựng đọc file bị lỗi, hãy bỏ tick **Dùng chung khung trùng** (hoặc dùng `--no-share`). File sẽ nặng hơn nhưng hình hoàn toàn giống nhau.

## Dòng lệnh

```bash
# Xuất ProRes cho đoạn 1:02:00–1:10:00, kích thước/FPS lấy theo video gốc
python chat_overlay.py stream.live_chat.json --video stream.mp4 --format prores --start 1:02:00 --end 1:10:00

# Tải chat từ link vào thư mục chỉ định rồi xuất luôn
python chat_overlay.py "https://www.youtube.com/watch?v=VIDEO_ID" --download-dir "D:/Chat" --video stream.mp4 --format ffv1

# Xem thử một khung hình tại 25:30
python chat_overlay.py stream.live_chat.json --video stream.mp4 --preview 25:30
```

Xem mọi tuỳ chọn bằng `python chat_overlay.py --help`:

- Giao diện: `--style`, `--position`, `--margin-x`, `--margin-y`, `--box-width`, `--font-size`.
- Nhịp tin: `--max-messages`, `--min-gap`, `--anim`, `--hide-after`; thời gian: `--offset`.
- An toàn: `--ignore-mismatch` vẫn xuất dù file chat và video có vẻ không cùng buổi live (mặc định lệnh dừng và giải thích).
- Đầu ra: `--format` (mặc định `prores`), `--canvas box|full`, `--no-share`, `--lang`.
- Thư mục: `--work-dir`, `--temp-dir`, `--cache-dir`, `--download-dir`.

### Chỉnh vị trí khung chat

Trên giao diện, chọn 1 trong 6 vị trí. Để tinh chỉnh khoảng cách tới mép hình, dùng `--margin-x` / `--margin-y`, hoặc sửa `class Options` trong `chat_overlay.py`:

```python
margin_x: int = 40   # trái/phải, px theo 1080p (tự co giãn cho 2K/4K)
margin_y: int = 40   # trên/dưới
```

Các lề này cũng được dùng để tính *Position X/Y* cho DaVinci in trong log. Sau đó bạn vẫn kéo clip tự do trong phần mềm dựng được.

## Mẹo và xử lý lỗi

- **“Không tìm thấy ffmpeg”:** cài FFmpeg và thêm thư mục `bin` vào `PATH`, hoặc chép `ffmpeg.exe` và `ffprobe.exe` cạnh app.
- **Tải chat lỗi:** bấm **Kiểm tra cập nhật yt-dlp** ở tab Tải video (YouTube hay đổi). Chỉ video đã từng livestream và còn bật chat replay mới có chat để tải. Video giới hạn tuổi hoặc dành cho hội viên cần `cookies.txt`.
- **Rớt mạng khi tải:** chat dài cần hàng trăm yêu cầu liên tiếp. App tự thử lại mỗi yêu cầu tối đa 10 lần, rồi tải lại đúng đoạn đó thêm tối đa 3 vòng, nên tải tiếp từ chỗ dừng. Log hiện dòng `⚠ Mất kết nối…`. Nếu vẫn lỗi, kiểm tra mạng, thử tắt VPN hoặc tính năng quét HTTPS của phần mềm diệt virus.
- **Dung lượng đĩa:** các khung hình khác nhau được dựng vào thư mục tạm trước khi mã hoá, khoảng 1–1,5 GB mỗi giờ chat ở 1080p. Hãy chọn *Thư mục làm việc* trên ổ còn trống. Đặt *Hiệu ứng trượt* = `0` giảm số khung khoảng 6 lần.
- **Font:** app tự tìm Segoe UI / Arial / Roboto / Noto Sans / DejaVu. Muốn dùng font riêng, chép `Roboto-Regular.ttf` và `Roboto-Medium.ttf` vào thư mục `fonts/` cạnh app, hoặc dùng `--font` và `--font-bold`.
- **Chat phản ứng chậm vài giây so với hình:** mỗi tin giữ đúng thời điểm nó đến YouTube, giống phần chat replay, và người xem vốn xem live chậm vài giây rồi mới gõ. Đặt *Dời thời gian* âm (vd `-5`) để mọi tin hiện sớm hơn.
- **Chữ bị mờ trong DaVinci:** đặt *Scaling = Crop* cho clip.
- **Lỗi “Permission denied” khi lưu:** nếu ô *Lưu thành* chỉ có tên file, file được lưu cạnh file chat. Kiểm tra thư mục đích có quyền ghi và file đích không đang mở trong phần mềm dựng.
- **Bấm đúp `ChatOverlay.pyw` báo "Activation is blocked due to the .appinstaller update settings":** file `.pyw` được mở bằng *Python Install Manager* và Windows chặn khi nó không tự cập nhật được. Cập nhật bằng PowerShell: `Add-AppxPackage -AppInstallerFile https://www.python.org/ftp/python/pymanager/pymanager.appinstaller` (nếu báo đang chạy, tắt `pyshellext.exe` trong Task Manager), hoặc dùng bản `.exe` ở mục [Tải về](#tải-về).

## Cách hoạt động

1. Tin nhắn được đọc từ JSON của yt-dlp (`videoOffsetTimeMsec`) và xếp hàng để mỗi tin hiện sau tin trước ít nhất `min_gap`.
2. Mỗi tin được vẽ một lần bằng Pillow.
3. Chỉ những khung hình mà chat thực sự thay đổi mới được dựng, song song trên mọi nhân CPU.
4. FFmpeg nén mỗi khung khác nhau một lần, thành chuỗi ảnh ở đúng tốc độ khung hình.
5. App ghi lại bảng mẫu của file MOV để mỗi khung đầu ra trỏ đúng khung đã nén. Khung trùng dùng chung dữ liệu, kết quả là file MOV tốc độ khung hình cố định bình thường.

## Giấy phép

[MIT](LICENSE).

Thành phần bên thứ ba:
- [FFmpeg](https://ffmpeg.org/legal.html) (LGPL/GPL): **không** đóng gói kèm, cài riêng.
- [Pillow](https://github.com/python-pillow/Pillow/blob/main/LICENSE) (MIT-CMU) và [yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE) (Unlicense): đóng gói sẵn trong các bản phát hành.

Khi đăng nội dung chat, hãy tôn trọng điều khoản của YouTube và quyền riêng tư của người xem.
