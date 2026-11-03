# ChatOverlay Cookie Export (browser extension)

**English** — A minimal, local-only Chrome/Edge/Brave extension that exports your YouTube/Google login cookies as a `cookies.txt` file, using the browser's own official `chrome.cookies` API (the same mechanism extensions like *Get cookies.txt LOCALLY* use). Nothing is uploaded anywhere; the file is saved straight to your computer.

**Why this exists:** the app's own "Get cookies" button reads the browser's cookie database directly, which only works while the browser is fully closed (the database is locked while it's running). This extension reads cookies through the browser itself instead, so it works with the browser open — the same way a cookie-export extension normally does.

**Install (one-time, "load unpacked"):**
1. Open `chrome://extensions` (or `edge://extensions`, `brave://extensions`).
2. Turn on **Developer mode** (top-right toggle).
3. Click **Load unpacked** and select this `browser-extension` folder.

**Use:**
1. Make sure you're logged into YouTube in that browser.
2. Click the extension's icon in the toolbar, then **Export cookies.txt**.
3. Save it as `cookies.txt` in your chat download folder (or wherever `chat_overlay.py` looks for it — see the main README).

---

**Tiếng Việt** — Tiện ích mở rộng nhỏ, chạy hoàn toàn cục bộ cho Chrome/Edge/Brave, xuất cookie đăng nhập YouTube/Google thành file `cookies.txt`, dùng đúng API `chrome.cookies` chính thức của trình duyệt (giống cách tiện ích *Get cookies.txt LOCALLY* hoạt động). Không gửi gì lên mạng; file được lưu thẳng vào máy bạn.

**Vì sao cần tiện ích này:** nút "Lấy cookies" trong app đọc thẳng file database của trình duyệt, nên chỉ chạy được khi trình duyệt đã đóng hẳn (file bị khoá lúc đang chạy). Tiện ích này đọc cookie qua chính trình duyệt thay vì đọc file, nên dùng được cả khi trình duyệt đang mở — đúng cách một tiện ích xuất cookie bình thường vẫn làm.

**Cài đặt (1 lần, "load unpacked"):**
1. Mở `chrome://extensions` (hoặc `edge://extensions`, `brave://extensions`).
2. Bật **Developer mode** (góc trên phải).
3. Bấm **Load unpacked**, chọn thư mục `browser-extension` này.

**Dùng:**
1. Đảm bảo bạn đã đăng nhập YouTube trên trình duyệt đó.
2. Bấm biểu tượng tiện ích trên thanh công cụ, rồi **Export cookies.txt**.
3. Lưu thành `cookies.txt` vào thư mục lưu chat tải về (hoặc nơi khác mà `chat_overlay.py` tìm — xem README chính).
