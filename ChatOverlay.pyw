# -*- coding: utf-8 -*-
"""
ChatOverlay.pyw — Windows launcher: double-click to open the app WITHOUT a console window.
Lần đầu chạy sẽ tự cài thư viện còn thiếu (Pillow, yt-dlp). Không cần quyền admin.

(.pyw files are run by pythonw.exe, which never opens a console window.)
"""
import importlib.util
import os
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REQUIRED = [("PIL", "pillow")]     # bắt buộc / required
OPTIONAL = [("yt_dlp", "yt-dlp")]  # chỉ để tải chat từ link / only for YouTube links
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def use_work_dir():
    """Đưa file tạm (kể cả khi pip cài thư viện) vào thư mục làm việc đã chọn, tránh ghi vào ổ C."""
    import json
    work = ""
    try:
        with open(os.path.join(HERE, "settings.json"), "r", encoding="utf-8") as f:
            work = json.load(f).get("work_dir", "")
    except Exception:
        pass
    tmp = os.path.join(work or os.path.join(HERE, "work"), "temp")
    try:
        os.makedirs(tmp, exist_ok=True)
        for var in ("TMP", "TEMP", "TMPDIR"):
            os.environ[var] = tmp
    except OSError:
        pass


def missing(pairs):
    return [pkg for mod, pkg in pairs if importlib.util.find_spec(mod) is None]


def pip_install(pkgs):
    out = ""
    for extra in ([], ["--user"]):
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", *extra, *pkgs],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                           creationflags=NO_WINDOW)
        out = r.stdout.decode("utf-8", "replace")
        if r.returncode == 0:
            return True, out
    return False, out[-1500:]


def install_with_splash(pkgs):
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.title("Chat Overlay")
    root.resizable(False, False)
    tk.Label(root, padx=28, pady=20, justify="left",
             text="Đang cài thư viện cho lần chạy đầu tiên…\nInstalling first-run dependencies…\n\n"
                  + ", ".join(pkgs)).pack()
    result = {}
    worker = threading.Thread(target=lambda: result.setdefault("r", pip_install(pkgs)), daemon=True)
    worker.start()

    def wait():
        if worker.is_alive():
            root.after(200, wait)
        else:
            root.destroy()
    root.after(200, wait)
    root.mainloop()
    ok, log = result.get("r", (False, ""))
    if not ok:
        box = tk.Tk()
        box.withdraw()
        messagebox.showerror("Chat Overlay", "pip install failed / Cài thư viện thất bại:\n\n" + log)
        box.destroy()
    return ok


def main():
    use_work_dir()
    need = missing(REQUIRED) + missing(OPTIONAL)
    if need:
        install_with_splash(need)
        importlib.invalidate_caches()
        if missing(REQUIRED):
            return
    import chat_overlay
    chat_overlay.main(["--gui"])


if __name__ == "__main__":
    main()
