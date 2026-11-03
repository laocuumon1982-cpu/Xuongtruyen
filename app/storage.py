"""Lưu cài đặt và truyện dưới dạng file JSON trong thư mục data/."""
import json
import os
import threading
import time
import uuid

from . import paths

_lock = threading.Lock()

DEFAULT_SETTINGS = {
    "provider": "builtin",
    "base_url": "http://127.0.0.1:8091/v1",
    "api_key": "",
    "model": "",
    "temperature": 0.85,
    "top_p": 0.95,
    "max_tokens": 4096,
    "context_chars": 24000,
    "no_think": True,
    "chapter_words": 2500,
    "ui_theme": "dark",
    "font_size": 18,
    "window_w": 1400,
    "window_h": 900,
    "check_update_on_start": True,
    "engine_port": 8091,
    "engine_ctx": 16384,
    "engine_model": "",
    "engine_autostart": True,
    "models_dir": "",
    "extra_model_dirs": [],
    "welcomed": False,
}

PROVIDER_PRESETS = {
    "builtin": {"label": "Có sẵn trong app (llama.cpp)", "base_url": "http://127.0.0.1:8091/v1"},
    "lmstudio": {"label": "LM Studio", "base_url": "http://127.0.0.1:1234/v1"},
    "ollama": {"label": "Ollama", "base_url": "http://127.0.0.1:11434/v1"},
    "koboldcpp": {"label": "KoboldCpp", "base_url": "http://127.0.0.1:5001/v1"},
    "llamacpp": {"label": "llama.cpp server", "base_url": "http://127.0.0.1:8080/v1"},
    "textgen": {"label": "text-generation-webui", "base_url": "http://127.0.0.1:5000/v1"},
    "custom": {"label": "Tùy chỉnh (OpenAI-compatible)", "base_url": ""},
}


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ---------------- Cài đặt ----------------
def load_settings():
    s = dict(DEFAULT_SETTINGS)
    s.update(_read_json(paths.settings_path(), {}))
    return s


def save_settings(new):
    with _lock:
        s = load_settings()
        for k, v in (new or {}).items():
            if k in DEFAULT_SETTINGS:
                s[k] = v
        _write_json(paths.settings_path(), s)
        return s


# ---------------- Truyện ----------------
def new_story(**kw):
    now = time.time()
    st = {
        "id": uuid.uuid4().hex[:12],
        "title": "Truyện chưa đặt tên",
        "logline": "",
        "genre": "",
        "style": "",
        "pov": "",
        "language": "Tiếng Việt",
        "rating": "all",
        "idea": "",
        "world": "",
        "notes": "",
        "characters": [],
        "chapters": [],
        "chat": [],
        "created": now,
        "updated": now,
    }
    st.update({k: v for k, v in kw.items() if k in st})
    return st


def _story_path(sid):
    safe = "".join(c for c in sid if c.isalnum() or c in "-_")
    return os.path.join(paths.stories_dir(), safe + ".json")


def list_stories():
    out = []
    for fn in os.listdir(paths.stories_dir()):
        if not fn.endswith(".json"):
            continue
        st = _read_json(os.path.join(paths.stories_dir(), fn), None)
        if not st or "id" not in st:
            continue
        chs = st.get("chapters", [])
        words = sum(len((c.get("content") or "").split()) for c in chs)
        out.append({
            "id": st["id"],
            "title": st.get("title", ""),
            "logline": st.get("logline", ""),
            "genre": st.get("genre", ""),
            "rating": st.get("rating", "all"),
            "chapters": len(chs),
            "written": sum(1 for c in chs if (c.get("content") or "").strip()),
            "words": words,
            "updated": st.get("updated", 0),
        })
    out.sort(key=lambda x: x["updated"], reverse=True)
    return out


def get_story(sid):
    return _read_json(_story_path(sid), None)


def save_story(st):
    with _lock:
        st["updated"] = time.time()
        _write_json(_story_path(st["id"]), st)
        return st


def delete_story(sid):
    p = _story_path(sid)
    if os.path.exists(p):
        os.remove(p)
