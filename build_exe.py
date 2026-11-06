# -*- coding: utf-8 -*-
"""
build_exe.py — đóng gói app thành ChatOverlay\\ChatOverlay.exe (bấm đúp là chạy, không cần cài Python).
Build the app into ChatOverlay\\ChatOverlay.exe (double-click to run, no Python needed).

    python build_exe.py

- Cập nhật yt-dlp trước khi build (YouTube hay đổi, yt-dlp cần mới). Cần có sẵn Pillow và PyInstaller.
  Updates yt-dlp first (YouTube changes often, yt-dlp must be recent). Needs Pillow and PyInstaller installed.
- Dạng thư mục (onedir), không phải 1 file: khởi động nhanh, không giải nén vào %TEMP% (ổ C) mỗi lần chạy.
  Folder build (onedir), not one-file: starts fast and never unpacks into %TEMP% (drive C) on each launch.
- File tạm của PyInstaller nằm trong thư mục làm việc (settings.json → work_dir), không ghi vào ổ C.
  PyInstaller's temp files go to the work folder (settings.json → work_dir), not drive C.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "ChatOverlay"
# Thư viện lớn có thể có sẵn trong môi trường Python nhưng app không dùng -> loại ra cho nhẹ.
# Big libraries that may be installed but are not used by the app -> keep them out of the build.
EXCLUDES = ["numpy", "scipy", "pandas", "matplotlib", "torch", "onnxruntime", "ctranslate2", "transformers",
            "huggingface_hub", "av", "imageio", "cv2", "PyQt5", "PyQt6", "PySide2", "PySide6", "IPython",
            "jupyter", "notebook", "pytest",
            "PIL._avif"]   # AVIF (7,8 MB) app không dùng: avatar/emoji là JPEG/PNG/WebP / AVIF unused (7.8 MB)


def work_dir():
    try:
        with open(os.path.join(HERE, "settings.json"), "r", encoding="utf-8") as f:
            w = json.load(f).get("work_dir", "")
        if w:
            return w
    except Exception:
        pass
    return os.path.join(HERE, "work")


def set_folder_icon(folder, icon=NAME + ".exe,0"):
    """Windows: thư mục ChatOverlay hiện logo của app trong Explorer (desktop.ini). / Folder shows the app logo."""
    if os.name != "nt":
        return
    ini = os.path.join(folder, "desktop.ini")
    if os.path.exists(ini):
        subprocess.run(["attrib", "-h", "-s", ini], check=False)
    with open(ini, "w", encoding="utf-16", newline="\r\n") as f:   # Explorer đọc được desktop.ini Unicode
        f.write(f"[.ShellClassInfo]\nIconResource={icon}\n")
    subprocess.run(["attrib", "+h", "+s", ini], check=False)
    subprocess.run(["attrib", "+r", folder], check=False)   # Explorer chỉ đọc desktop.ini khi thư mục có cờ R/S
    refresh_icons(folder)


def refresh_icons(path=None):
    """Báo Explorer vẽ lại biểu tượng, không cần khởi động lại máy. / Tell Explorer to redraw icons."""
    if os.name != "nt":
        return
    import ctypes
    shell32 = ctypes.windll.shell32
    if path:
        shell32.SHChangeNotify(0x00002000, 0x0005, ctypes.c_wchar_p(path), None)   # SHCNE_UPDATEITEM, SHCNF_PATHW
    shell32.SHChangeNotify(0x08000000, 0x0000, None, None)                         # SHCNE_ASSOCCHANGED


def run(cmd, **kw):
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def main():
    work = os.path.join(work_dir(), "pyinstaller")
    os.makedirs(work, exist_ok=True)
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=os.path.join(work, "config"),
               TMP=os.path.join(work, "tmp"), TEMP=os.path.join(work, "tmp"))
    os.makedirs(env["TMP"], exist_ok=True)

    run([sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", "yt-dlp"], env=env)
    need = [p for m, p in (("PIL", "pillow"), ("PyInstaller", "pyinstaller")) if importlib.util.find_spec(m) is None]
    if need:
        run([sys.executable, "-m", "pip", "install", "--no-cache-dir", *need], env=env)

    dist = os.path.join(HERE, NAME)
    kept = None
    if os.path.isdir(dist):
        try:                         # giữ cài đặt của bản .exe cũ / keep the old build's settings
            with open(os.path.join(dist, "settings.json"), "rb") as f:
                kept = f.read()
        except OSError:
            pass
        if os.name == "nt":
            subprocess.run(["attrib", "-r", dist], check=False)
        shutil.rmtree(dist)          # bản build cũ / previous build
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
           "--name", NAME, "--distpath", HERE, "--workpath", os.path.join(work, "build"),
           "--specpath", work,
           "--icon", os.path.join(HERE, "assets", "icon.ico"),                    # logo file .exe / exe icon
           "--add-data", os.path.join(HERE, "assets") + os.pathsep + "assets"]    # logo cửa sổ / window icon
    for m in EXCLUDES:
        cmd += ["--exclude-module", m]
    run(cmd + [os.path.join(HERE, "chat_overlay.py")], env=env)

    # Cài đặt: giữ của bản .exe cũ, nếu chưa có thì chép từ bản .py
    # Settings: keep the old build's, otherwise copy the .py version's
    src, dst = os.path.join(HERE, "settings.json"), os.path.join(dist, "settings.json")
    if kept is not None:
        with open(dst, "wb") as f:
            f.write(kept)
    elif os.path.isfile(src):
        shutil.copy2(src, dst)
    # Dữ liệu múi giờ của Tcl (~2 MB) app không dùng. / Tcl time-zone data (~2 MB) is unused by the app.
    shutil.rmtree(os.path.join(dist, "_internal", "_tcl_data", "tzdata"), ignore_errors=True)
    set_folder_icon(dist)
    print("\nDONE / XONG:", os.path.join(dist, NAME + ".exe"))


if __name__ == "__main__":
    main()
