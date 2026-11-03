"""Kiểm tra và cập nhật bản mới từ GitHub Releases (giữ nguyên thư mục data/)."""
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from . import paths
from .version import APP_VERSION, GITHUB_REPO

API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"


def _vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:4]) or (0,)


def check():
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "XuongTruyen-Updater"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    tag = data.get("tag_name", "")
    asset = None
    for a in data.get("assets", []):
        n = a.get("name", "").lower()
        if n.endswith(".zip") and "portable" in n:
            asset = a
            break
    return {
        "current": APP_VERSION,
        "latest": tag.lstrip("vV"),
        "has_update": _vtuple(tag) > _vtuple(APP_VERSION),
        "notes": data.get("body") or "",
        "url": asset["browser_download_url"] if asset else None,
        "size": asset.get("size") if asset else 0,
        "page": data.get("html_url") or RELEASES_PAGE,
        "can_self_update": bool(getattr(sys, "frozen", False) and os.name == "nt"),
    }


def download(url, progress=None):
    """Tải file zip về thư mục tạm. progress(done, total)."""
    tmpdir = tempfile.mkdtemp(prefix="xuongtruyen_upd_")
    zpath = os.path.join(tmpdir, "update.zip")
    req = urllib.request.Request(url, headers={"User-Agent": "XuongTruyen-Updater"})
    with urllib.request.urlopen(req, timeout=60) as r, open(zpath, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            buf = r.read(256 * 1024)
            if not buf:
                break
            f.write(buf)
            done += len(buf)
            if progress:
                progress(done, total)
    return tmpdir, zpath


def apply_and_restart(tmpdir, zpath):
    """Giải nén bản mới rồi chạy script .bat thay file sau khi app thoát (chỉ Windows, bản build)."""
    extract = os.path.join(tmpdir, "new")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(extract)
    # zip có thể chứa sẵn thư mục XuongTruyen/ bên trong
    src = extract
    entries = os.listdir(extract)
    if len(entries) == 1 and os.path.isdir(os.path.join(extract, entries[0])):
        src = os.path.join(extract, entries[0])
    target = paths.app_dir()
    exe = os.path.join(target, os.path.basename(sys.executable))
    pid = os.getpid()
    bat = os.path.join(tmpdir, "update.bat")
    with open(bat, "w", encoding="utf-8") as f:
        f.write(
            "@echo off\r\nchcp 65001 >nul\r\n"
            "echo Dang cap nhat Xuong Truyen, vui long doi...\r\n"
            f":wait\r\ntasklist /FI \"PID eq {pid}\" 2>nul | find \"{pid}\" >nul\r\n"
            "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)\r\n"
            f"robocopy \"{src}\" \"{target}\" /E /XD data /R:3 /W:1 /NFL /NDL /NJH /NJS >nul\r\n"
            f"start \"\" \"{exe}\"\r\n"
            f"rmdir /s /q \"{extract}\"\r\n"
            "exit\r\n"
        )
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(["cmd", "/c", bat], creationflags=flags, close_fds=True)
    os._exit(0)
