// Manual "Export cookies.txt" button — same data as the automatic native-messaging
// link (background.js), saved via a download dialog instead.
const statusEl = document.getElementById("status");

document.getElementById("export").addEventListener("click", async () => {
  statusEl.textContent = "Đang đọc cookies…";
  try {
    const { text, count } = await collectCookiesText();
    if (count === 0) {
      statusEl.textContent = "Không tìm thấy cookie nào của youtube.com. Hãy đăng nhập YouTube rồi thử lại.";
      return;
    }
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    chrome.downloads.download({ url, filename: "cookies.txt", saveAs: true }, (downloadId) => {
      if (chrome.runtime.lastError || downloadId === undefined) {
        statusEl.textContent = "Lỗi: " + (chrome.runtime.lastError?.message || "không lưu được file.");
      } else {
        statusEl.textContent = `Đã lưu ${count} cookie vào cookies.txt.`;
      }
      URL.revokeObjectURL(url);
    });
  } catch (e) {
    statusEl.textContent = "Lỗi: " + e.message;
  }
});
