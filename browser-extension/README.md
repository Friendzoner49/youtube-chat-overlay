# ChatOverlay Cookie Export (browser extension)

**English** — A minimal, local-only Chrome/Edge extension that gives the ChatOverlay app your YouTube login cookies, using the browser's own official `chrome.cookies` API (the same mechanism extensions like *Get cookies.txt LOCALLY* use). Nothing is uploaded anywhere.

**Why this exists:** the app's own "Get cookies" button reads the browser's cookie database directly, which only works while the browser is fully closed (the database is locked while it's running). This extension reads cookies through the browser itself instead, so it works with the browser left open.

**Two ways it's used, once installed:**
- **Direct link (automatic, Windows only):** the extension keeps a connection open to the ChatOverlay app (native messaging). Press the app's **Get cookies** button with the browser open and logged into YouTube — it talks to the extension directly and saves `cookies.txt`, no extra click needed. The app registers this link itself the first time it runs; you only need to load the extension once (steps below) and keep it enabled.
- **Manual export (any OS, if the direct link isn't set up):** click the extension's toolbar icon → **Export cookies.txt** → save it into the app's chat download folder yourself.

**Install (one-time, "load unpacked"):**
1. Open `chrome://extensions` (or `edge://extensions`).
2. Turn on **Developer mode** (top-right toggle).
3. Click **Load unpacked** and select this `browser-extension` folder (load it from the actual project folder, not a temp/zip extraction you might delete later — if you move it, reload the extension from the new location).
4. Check the extension's ID shown on that page is `kmmooalecgnnejbbmniogbljiikjcnoh` — the app is only allowed to talk to that exact ID (this is pinned in `manifest.json`'s `"key"` field so the ID never changes, even across reinstalls).

**If the direct link doesn't connect:** reload the extension (circular arrow icon on `chrome://extensions`) or restart the browser so its background script reconnects, then try the app's button again. If it still falls back to asking you to close the browser, use the manual export instead.

---

**Tiếng Việt** — Tiện ích mở rộng nhỏ, chạy hoàn toàn cục bộ cho Chrome/Edge, cho app ChatOverlay quyền dùng cookie đăng nhập YouTube của bạn, qua đúng API `chrome.cookies` chính thức của trình duyệt (giống cách tiện ích *Get cookies.txt LOCALLY* hoạt động). Không gửi gì lên mạng.

**Vì sao cần tiện ích này:** nút "Lấy cookies" trong app đọc thẳng file database của trình duyệt, nên chỉ chạy được khi trình duyệt đã đóng hẳn (file bị khoá lúc đang chạy). Tiện ích này đọc cookie qua chính trình duyệt thay vì đọc file, nên dùng được cả khi trình duyệt đang mở.

**2 cách dùng, sau khi đã cài:**
- **Kết nối trực tiếp (tự động, chỉ Windows):** tiện ích giữ kết nối với app ChatOverlay (native messaging). Cứ bấm nút **Lấy cookies** trong app khi trình duyệt đang mở và đã đăng nhập YouTube — app sẽ nói chuyện thẳng với tiện ích và lưu `cookies.txt`, không cần bấm thêm gì trong trình duyệt. App tự đăng ký kết nối này ngay lần chạy đầu tiên; bạn chỉ cần nạp tiện ích 1 lần (xem bước dưới) và để nó bật.
- **Xuất thủ công (mọi hệ điều hành, khi chưa có kết nối trực tiếp):** bấm icon tiện ích trên thanh công cụ → **Export cookies.txt** → tự lưu vào thư mục lưu chat của app.

**Cài đặt (1 lần, "load unpacked"):**
1. Mở `chrome://extensions` (hoặc `edge://extensions`).
2. Bật **Developer mode** (góc trên phải).
3. Bấm **Load unpacked**, chọn thư mục `browser-extension` này (nạp từ đúng thư mục dự án, đừng nạp từ bản giải nén tạm rồi xoá đi — nếu di chuyển thư mục, nạp lại tiện ích từ vị trí mới).
4. Kiểm tra ID tiện ích hiện trên trang đó đúng là `kmmooalecgnnejbbmniogbljiikjcnoh` — app chỉ cho phép đúng ID này nói chuyện với nó (đã cố định trong `manifest.json`, mục `"key"`, nên ID không đổi dù cài lại).

**Nếu kết nối trực tiếp không chạy:** nạp lại tiện ích (icon mũi tên tròn ở `chrome://extensions`) hoặc khởi động lại trình duyệt để nền của tiện ích kết nối lại, rồi bấm nút trong app lần nữa. Nếu vẫn rơi về yêu cầu đóng trình duyệt, dùng cách xuất thủ công ở trên.
