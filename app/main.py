"""Khởi động Xưởng Truyện: chạy server nội bộ rồi mở cửa sổ app."""
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser

from . import server, storage
from .version import APP_NAME, APP_VERSION


def _free_port(preferred=8765):
    for p in (preferred, 0):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            s.close()
    return 0


def _find_edge():
    cands = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    for name in ("msedge", "chrome", "chromium", "google-chrome"):
        w = shutil.which(name)
        if w:
            return w
    return None


def _browser_mode(url):
    """Không có pywebview: mở bằng Edge/Chrome chế độ app, tự tắt khi đóng cửa sổ."""
    exe = _find_edge()
    if exe:
        subprocess.Popen([exe, f"--app={url}", "--window-size=1400,900"])
    else:
        webbrowser.open(url)
    server.LAST_PING[0] = time.time() + 60  # cho thời gian mở trình duyệt
    while True:
        time.sleep(5)
        if time.time() - server.LAST_PING[0] > 45:
            os._exit(0)


def main():
    port = _free_port()
    srv = server.make_server(port)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"{APP_NAME} {APP_VERSION} đang chạy tại {url}")

    if "--browser" in sys.argv:
        return _browser_mode(url)
    try:
        import webview
    except Exception:  # noqa
        return _browser_mode(url)

    s = storage.load_settings()
    win = webview.create_window(
        f"{APP_NAME} {APP_VERSION}", url,
        width=int(s.get("window_w", 1400)), height=int(s.get("window_h", 900)),
        min_size=(980, 640), text_select=True,
    )
    server.WINDOW = win

    def on_closing():
        try:
            storage.save_settings({"window_w": win.width, "window_h": win.height})
        except Exception:  # noqa
            pass

    win.events.closing += on_closing
    try:
        webview.start(private_mode=False, storage_path=os.path.join(storage.paths.data_dir(), "webview"))
    except Exception:  # noqa
        server.WINDOW = None
        return _browser_mode(url)
    os._exit(0)


if __name__ == "__main__":
    main()
