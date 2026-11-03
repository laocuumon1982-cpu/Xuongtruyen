"""Đường dẫn cho bản portable: dữ liệu nằm cạnh file exe (thư mục data/)."""
import os
import sys


def app_dir() -> str:
    """Thư mục chứa exe (bản build) hoặc thư mục gốc dự án (khi chạy source)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir() -> str:
    """Nơi chứa file giao diện web (đóng gói bên trong bản build)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "app")
    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    d = os.environ.get("XUONGTRUYEN_DATA") or os.path.join(app_dir(), "data")
    os.makedirs(d, exist_ok=True)
    return d


def stories_dir() -> str:
    d = os.path.join(data_dir(), "stories")
    os.makedirs(d, exist_ok=True)
    return d


def exports_dir() -> str:
    d = os.path.join(data_dir(), "exports")
    os.makedirs(d, exist_ok=True)
    return d


def settings_path() -> str:
    return os.path.join(data_dir(), "settings.json")
