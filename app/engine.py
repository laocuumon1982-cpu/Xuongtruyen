"""Bộ máy chạy model tích hợp (llama.cpp llama-server) + tải model GGUF từ HuggingFace."""
import atexit
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

from . import paths, storage

GH_API = os.environ.get("XT_GH_API", "https://api.github.com")
HF_BASE = os.environ.get("XT_HF_BASE", "https://huggingface.co")
UA = {"User-Agent": "XuongTruyen"}
IS_WIN = os.name == "nt"
NO_WINDOW = 0x08000000 if IS_WIN else 0
SERVER_EXE = "llama-server.exe" if IS_WIN else "llama-server"

# ----------------------------------------------------------------------------
# Danh sách model đề xuất (đều là bản đã gỡ kiểm duyệt, viết được 18+/NSFW)
# ----------------------------------------------------------------------------
CATALOG = [
    {
        "id": "gemma4-12b", "name": "Gemma 4 12B Abliterated", "featured": True,
        "repo": "mradermacher/gemma-4-12B-it-abliterated-uncensored-GGUF", "quant": "Q5_K_M", "size_gb": 8.6,
        "lang": "vi", "speed": "Rất nhanh – chạy hết trên GPU 12GB",
        "desc": "Đề xuất số 1 cho máy bạn. Tiếng Việt tốt, không kiểm duyệt, viết được truyện 18+/NSFW, khoa học viễn tưởng, mọi thể loại.",
    },
    {
        "id": "gemma4-26b-a4b", "name": "Gemma 4 26B-A4B Heretic (MoE)",
        "repo": "mradermacher/gemma-4-26B-A4B-it-heretic-GGUF", "quant": "Q4_K_M", "size_gb": 16.8,
        "lang": "vi", "speed": "Khá nhanh – tràn một phần sang RAM nhưng là MoE nên vẫn mượt",
        "desc": "Thông minh và viết hay hơn bản 12B, tiếng Việt tốt, không kiểm duyệt. Cần RAM 32GB.",
    },
    {
        "id": "qwen36-27b", "name": "Qwen 3.6 27B Abliterated",
        "repo": "mradermacher/Huihui-Qwen3.6-27B-abliterated-GGUF", "quant": "Q4_K_M", "size_gb": 16.6,
        "lang": "vi", "speed": "Chậm (khoảng 3–6 chữ/giây) – tràn sang RAM",
        "desc": "Viết hay nhất, giữ mạch truyện dài tốt, tiếng Việt tốt, không kiểm duyệt. Hợp khi viết chậm mà chất.",
    },
    {
        "id": "qwen3-14b", "name": "Qwen3 14B Abliterated",
        "repo": "bartowski/huihui-ai_Qwen3-14B-abliterated-GGUF", "quant": "Q5_K_M", "size_gb": 10.5,
        "lang": "vi", "speed": "Nhanh – vừa khít GPU 12GB",
        "desc": "Cân bằng tốc độ và chất lượng, tiếng Việt khá, không kiểm duyệt.",
    },
    {
        "id": "rocinante-12b", "name": "Rocinante 12B (tiếng Anh)",
        "repo": "TheDrummer/Rocinante-12B-v1.1-GGUF", "quant": "Q5_K_M", "size_gb": 8.7,
        "lang": "en", "speed": "Rất nhanh – chạy hết trên GPU",
        "desc": "Chuyên viết truyện & roleplay 18+/NSFW bằng tiếng Anh, văn phong sống động. Tiếng Việt yếu.",
    },
    {
        "id": "cydonia-24b", "name": "Cydonia 24B (tiếng Anh)",
        "repo": "TheDrummer/Cydonia-24B-v2.1-GGUF", "quant": "Q4_K_M", "size_gb": 14.3,
        "lang": "en", "speed": "Trung bình – tràn một phần sang RAM",
        "desc": "Bản lớn hơn của dòng truyện 18+ tiếng Anh, thông minh, viết dài tốt. Tiếng Việt yếu.",
    },
]
QUANT_FALLBACK = ["Q5_K_M", "Q4_K_M", "Q4_K_S", "Q5_K_S", "IQ4_XS", "Q6_K", "Q8_0", "Q3_K_L", "Q3_K_M"]


# ----------------------------------------------------------------------------
# Thư mục
# ----------------------------------------------------------------------------
def engine_dir():
    d = os.path.join(paths.data_dir(), "engine")
    os.makedirs(d, exist_ok=True)
    return d


def models_dir():
    d = storage.load_settings().get("models_dir") or os.path.join(paths.data_dir(), "models")
    os.makedirs(d, exist_ok=True)
    return d


def extra_model_dirs():
    home = os.path.expanduser("~")
    dirs = [os.path.join(home, ".lmstudio", "models"), os.path.join(home, ".cache", "lm-studio", "models")]
    dirs += storage.load_settings().get("extra_model_dirs") or []
    return [d for d in dirs if d and os.path.isdir(d)]


# ----------------------------------------------------------------------------
# Tác vụ chạy nền (tải engine / tải model) – giao diện hỏi tiến độ định kỳ
# ----------------------------------------------------------------------------
TASKS = {}
_tlock = threading.Lock()


class Cancelled(Exception):
    pass


def _new_task(kind, label, key=None):
    tid = uuid.uuid4().hex[:8]
    t = {"id": tid, "kind": kind, "label": label, "key": key, "state": "running", "msg": "Đang chuẩn bị…",
         "done": 0, "total": 0, "speed": 0, "cancel": False, "started": time.time()}
    with _tlock:
        TASKS[tid] = t
    return t


def task_list():
    with _tlock:
        now = time.time()
        for k in [k for k, t in TASKS.items() if t["state"] != "running" and now - t.get("ended", now) > 600]:
            TASKS.pop(k, None)
        return [{k: v for k, v in t.items() if k != "cancel"} for t in TASKS.values()]


def cancel_task(tid):
    t = TASKS.get(tid)
    if t:
        t["cancel"] = True


def _run_task(t, fn):
    def wrap():
        try:
            fn(t)
            if t["state"] == "running":
                t["state"] = "done"
        except Cancelled:
            t["state"], t["msg"] = "cancelled", "Đã huỷ"
        except Exception as e:  # noqa
            t["state"], t["msg"] = "error", f"Lỗi: {e}"
        t["ended"] = time.time()
    threading.Thread(target=wrap, daemon=True).start()
    return t


def _http_json(url, timeout=30):
    req = urllib.request.Request(url, headers=dict(UA, Accept="application/json"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _download(url, dest, t, label=""):
    """Tải file có hỗ trợ tải tiếp (resume) nếu bị ngắt."""
    part = dest + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    headers = dict(UA)
    if have:
        headers["Range"] = f"bytes={have}-"
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(5):
        try:
            r = urllib.request.urlopen(req, timeout=60)
            break
        except urllib.error.HTTPError as e:
            if e.code == 416:  # đã tải đủ
                os.replace(part, dest)
                return
            if attempt == 4 or e.code in (401, 403, 404):
                raise
        except urllib.error.URLError:
            if attempt == 4:
                raise
        time.sleep(2 + attempt * 2)
    with r:
        if have and r.status != 206:
            have = 0  # server không hỗ trợ resume -> tải lại từ đầu
        total = int(r.headers.get("Content-Length") or 0) + have
        t["total_file"] = total
        mode = "ab" if have else "wb"
        last_t, last_b = time.time(), have
        done = have
        with open(part, mode) as f:
            while True:
                if t["cancel"]:
                    raise Cancelled()
                buf = r.read(1024 * 1024)
                if not buf:
                    break
                f.write(buf)
                done += len(buf)
                now = time.time()
                if now - last_t >= 0.7:
                    t["speed"] = (done - last_b) / (now - last_t)
                    last_t, last_b = now, done
                t["file_done"] = done
                t["done"] = t.get("base_done", 0) + done
                if label:
                    t["msg"] = label
    if total and os.path.getsize(part) < total - 1:
        raise IOError("Tải chưa đủ dung lượng, hãy bấm tải lại để tải tiếp.")
    os.replace(part, dest)


# ----------------------------------------------------------------------------
# GPU & engine
# ----------------------------------------------------------------------------
def gpu_info():
    exe = shutil.which("nvidia-smi") or (r"C:\Windows\System32\nvidia-smi.exe" if IS_WIN else None)
    if not exe or not os.path.exists(exe):
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total,memory.free,driver_version",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=8,
                             creationflags=NO_WINDOW).stdout.strip().splitlines()
        name, total, free, drv = [x.strip() for x in out[0].split(",")]
        return {"name": name, "total_mb": int(total), "free_mb": int(free), "driver": drv}
    except Exception:  # noqa
        return None


def _find_server_exe():
    d = engine_dir()
    for root, _, files in os.walk(d):
        if SERVER_EXE in files:
            return os.path.join(root, SERVER_EXE)
    return None


def engine_info():
    exe = _find_server_exe()
    meta = {}
    try:
        with open(os.path.join(engine_dir(), "engine.json"), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        pass
    return {"installed": bool(exe), "exe": exe, "version": meta.get("version", ""), "backend": meta.get("backend", "")}


def default_backend():
    g = gpu_info()
    if g:
        return "cuda12"
    return "vulkan"


def _pick_assets(assets, backend, fallback=True):
    """Chọn gói Windows x64 phù hợp. Chấp nhận cả kiểu tên mới (cuda-12.4) lẫn cũ (cuda-cu12.4).
    fallback=False: chỉ nhận đúng loại yêu cầu (CUDA phải kèm gói cudart)."""
    names = {a["name"]: a for a in assets}

    def find(rx):
        for n, a in names.items():
            if re.match(rx, n, re.I):
                return a
        return None

    if backend.startswith("cuda"):
        majors = [backend[4:] or "12"]
        if fallback:
            majors += [m for m in ("12", "13") if m not in majors]
        for major in majors:
            main = find(rf"^llama-.*-bin-win-cuda-(cu)?{major}[\d.]*-x64\.zip$")
            if main:
                ver = re.search(r"cuda-(?:cu)?([\d.]+)-x64", main["name"], re.I).group(1)
                rt = find(rf"^cudart-llama-bin-win-(cuda-)?(cu)?{re.escape(ver)}-x64\.zip$")
                if rt:
                    return [main, rt]
                if fallback:
                    return [main]
        if not fallback:
            return []
    if backend.startswith("cuda") or backend == "vulkan":
        a = find(r"^llama-.*-bin-win-vulkan-x64\.zip$")
        if a:
            return [a]
        if not fallback:
            return []
    a = find(r"^llama-.*-bin-win-(cpu|avx2)-x64\.zip$")
    return [a] if a else []


def _find_release(backend):
    """llama.cpp đánh dấu mọi bản là pre-release nên /releases/latest không dùng được –
    quét các bản mới nhất và lấy bản đầu tiên có đủ gói Windows."""
    base = f"{GH_API}/repos/ggml-org/llama.cpp/releases"
    try:
        rels = _http_json(base + "?per_page=15")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise RuntimeError("GitHub tạm giới hạn lượt truy cập (rate limit). Đợi khoảng 1 tiếng rồi thử lại, "
                               "hoặc dùng nút “Chọn file .zip llama.cpp” để cài thủ công.")
        raise
    rels = [r for r in (rels if isinstance(rels, list) else []) if not r.get("draft")]
    # lượt 1: đúng loại yêu cầu (CUDA phải có cả gói cudart); lượt 2: chấp nhận bản dự phòng
    for strict in (True, False):
        for rel in rels:
            assets = _pick_assets(rel.get("assets", []), backend, fallback=not strict)
            if assets:
                return rel, assets
    try:
        rel = _http_json(base + "/latest")
        assets = _pick_assets(rel.get("assets", []), backend)
        if assets:
            return rel, assets
    except Exception:  # noqa
        pass
    raise RuntimeError("Không tìm thấy gói llama.cpp cho Windows trên GitHub. Hãy thử lại sau ít phút, "
                       "hoặc tải thủ công rồi bấm “Chọn file .zip llama.cpp”.")


def _install_zips(zips, version, backend, t=None):
    if t:
        t["msg"] = "Đang giải nén…"
    stop_server()
    target = os.path.join(engine_dir(), "bin")
    if os.path.isdir(target):
        shutil.rmtree(target, ignore_errors=True)
    os.makedirs(target, exist_ok=True)
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            zf.extractall(target)
    exe = _find_server_exe()
    if not exe:
        raise RuntimeError("Gói này không có llama-server. Hãy chọn gói llama-…-bin-win-…-x64.zip.")
    if not IS_WIN:
        os.chmod(exe, 0o755)
    with open(os.path.join(engine_dir(), "engine.json"), "w", encoding="utf-8") as f:
        json.dump({"version": version, "backend": backend, "assets": [os.path.basename(z) for z in zips]}, f)


def install_engine_from_files(files):
    """Cài thủ công từ các file .zip người dùng đã tải về (gói llama + gói cudart nếu có)."""
    files = [f for f in files if f and os.path.isfile(f)]
    if not files:
        raise RuntimeError("Chưa chọn file .zip")
    names = " ".join(os.path.basename(f).lower() for f in files)
    backend = "cuda" if "cuda" in names else ("vulkan" if "vulkan" in names else "cpu")
    m = re.search(r"llama-(b\d+)-", names)
    _install_zips(files, m.group(1) if m else "thủ công", backend)
    return engine_info()


def install_engine(backend=None):
    backend = backend or default_backend()
    for t in TASKS.values():
        if t["kind"] == "engine" and t["state"] == "running":
            return t
    t = _new_task("engine", "Bộ máy chạy model (llama.cpp)", key="engine")

    def job(t):
        t["msg"] = "Đang tìm bản llama.cpp mới nhất…"
        rel, assets = _find_release(backend)
        t["total"] = sum(a.get("size", 0) for a in assets)
        tmp = os.path.join(engine_dir(), "_dl")
        os.makedirs(tmp, exist_ok=True)
        zips = []
        base = 0
        for a in assets:
            t["base_done"] = base
            dest = os.path.join(tmp, a["name"])
            _download(a["browser_download_url"], dest, t, f"Đang tải {a['name']}…")
            zips.append(dest)
            base += a.get("size", 0)
        _install_zips(zips, rel.get("tag_name", ""), backend, t)
        shutil.rmtree(tmp, ignore_errors=True)
        t["msg"] = f"Đã cài llama.cpp {rel.get('tag_name', '')} ({backend})"
    return _run_task(t, job)


# ----------------------------------------------------------------------------
# Model
# ----------------------------------------------------------------------------
def _repo_dir(repo):
    return os.path.join(models_dir(), repo.replace("/", "__"))


def resolve_files(repo, quant):
    """Hỏi HuggingFace danh sách file GGUF và chọn đúng bản nén (hỗ trợ file chia nhiều phần)."""
    items = _http_json(f"{HF_BASE}/api/models/{repo}/tree/main?recursive=true")
    ggufs = [i for i in items if i.get("type") == "file" and i["path"].lower().endswith(".gguf")
             and "mmproj" not in i["path"].lower()]
    if not ggufs:
        raise RuntimeError(f"Repo {repo} không có file GGUF.")
    order = [quant] + [q for q in QUANT_FALLBACK if q != quant]
    for q in order:
        rx = re.compile(r"(^|[^A-Za-z0-9])" + re.escape(q) + r"([^A-Za-z0-9]|$)", re.I)
        hits = [i for i in ggufs if rx.search(os.path.basename(i["path"]))]
        hits = [i for i in hits if not re.search(r"(^|[^a-z])i1([^a-z]|$)", i["path"], re.I)] or hits
        if hits:
            split = [i for i in hits if re.search(r"-\d{5}-of-\d{5}\.gguf$", i["path"])]
            if split:
                first = sorted(split, key=lambda i: i["path"])[0]
                prefix = re.sub(r"-\d{5}-of-\d{5}\.gguf$", "", first["path"])
                files = sorted([i for i in split if i["path"].startswith(prefix)], key=lambda i: i["path"])
            else:
                files = [sorted(hits, key=lambda i: len(i["path"]))[0]]
            return q, [{"path": f["path"], "size": f.get("size") or (f.get("lfs") or {}).get("size", 0)} for f in files]
    raise RuntimeError(f"Không tìm thấy bản {quant} trong {repo}.")


def model_main_path(repo, files):
    return os.path.join(_repo_dir(repo), os.path.basename(files[0]["path"]))


def download_model(repo, quant, name=None, start_after=False, catalog_id=None):
    key = f"{repo}:{quant}"
    for t in TASKS.values():
        if t.get("key") == key and t["state"] == "running":
            return t
    t = _new_task("model", name or repo, key=key)
    t["catalog_id"] = catalog_id

    def job(t):
        t["msg"] = "Đang hỏi HuggingFace danh sách file…"
        q, files = resolve_files(repo, quant)
        t["quant"] = q
        t["total"] = sum(f["size"] for f in files)
        d = _repo_dir(repo)
        os.makedirs(d, exist_ok=True)
        base = 0
        for k, f in enumerate(files, 1):
            dest = os.path.join(d, os.path.basename(f["path"]))
            if os.path.exists(dest) and (not f["size"] or os.path.getsize(dest) == f["size"]):
                base += f["size"]
                t["done"] = base
                continue
            t["base_done"] = base
            url = f"{HF_BASE}/{repo}/resolve/main/{urllib.parse.quote(f['path'])}?download=true"
            part = f" (phần {k}/{len(files)})" if len(files) > 1 else ""
            _download(url, dest, t, f"Đang tải {os.path.basename(f['path'])}{part}…")
            base += f["size"]
        t["path"] = model_main_path(repo, files)
        with open(os.path.join(d, "xt_model.json"), "w", encoding="utf-8") as fp:
            json.dump({"repo": repo, "quant": q, "name": name or repo, "catalog_id": catalog_id,
                       "main": os.path.basename(files[0]["path"])}, fp, ensure_ascii=False)
        t["msg"] = "Đã tải xong"
        if start_after:
            if not engine_info()["installed"]:
                et = install_engine()
                while et["state"] == "running":
                    if t["cancel"]:
                        raise Cancelled()
                    t["msg"] = "Đang chờ cài bộ máy chạy model… " + et["msg"]
                    time.sleep(1)
                if et["state"] != "done":
                    raise RuntimeError("Cài bộ máy chạy model thất bại: " + et["msg"])
            start_server(t["path"], name=name)
            t["msg"] = "Đã tải xong – đang nạp model"
    return _run_task(t, job)


def _split_first(fn):
    m = re.search(r"-(\d{5})-of-\d{5}\.gguf$", fn)
    return (m is None) or m.group(1) == "00001"


def local_models():
    seen, out = set(), []
    roots = [(models_dir(), "app")] + [(d, "lmstudio" if "lm" in d.lower() else "folder") for d in extra_model_dirs()]
    catalog_by_repo = {c["repo"]: c for c in CATALOG}
    for root, src in roots:
        for dp, _, files in os.walk(root):
            meta = {}
            if "xt_model.json" in files:
                try:
                    with open(os.path.join(dp, "xt_model.json"), encoding="utf-8") as f:
                        meta = json.load(f)
                except (OSError, ValueError):
                    pass
            for fn in files:
                if not fn.lower().endswith(".gguf") or "mmproj" in fn.lower() or not _split_first(fn):
                    continue
                p = os.path.join(dp, fn)
                rp = os.path.realpath(p)
                if rp in seen:
                    continue
                seen.add(rp)
                size = os.path.getsize(p)
                if re.search(r"-00001-of-\d{5}\.gguf$", fn):
                    pre = re.sub(r"-00001-of-\d{5}\.gguf$", "", fn)
                    size = sum(os.path.getsize(os.path.join(dp, x)) for x in files if x.startswith(pre) and x.endswith(".gguf"))
                cat = catalog_by_repo.get(meta.get("repo", ""))
                out.append({"path": p, "file": fn, "size": size, "source": src,
                            "name": (cat or {}).get("name") or meta.get("name") or re.sub(r"\.gguf$", "", fn),
                            "catalog_id": (cat or {}).get("id") or meta.get("catalog_id")})
    out.sort(key=lambda m: (m["source"] != "app", m["name"].lower()))
    return out


def delete_model(path):
    path = os.path.realpath(path)
    root = os.path.realpath(models_dir())
    if not path.startswith(root + os.sep):
        raise RuntimeError("Chỉ xoá được model nằm trong thư mục model của app.")
    if SERVER["model"] and os.path.realpath(SERVER["model"]) == path:
        stop_server()
    d = os.path.dirname(path)
    fn = os.path.basename(path)
    pre = re.sub(r"-00001-of-\d{5}\.gguf$", "", fn)
    for x in os.listdir(d):
        if x == fn or (pre != fn and x.startswith(pre) and x.endswith(".gguf")):
            os.remove(os.path.join(d, x))
    if not [x for x in os.listdir(d) if x.endswith(".gguf")]:
        shutil.rmtree(d, ignore_errors=True)


def catalog():
    loc = {m["catalog_id"]: m for m in local_models() if m.get("catalog_id")}
    out = []
    for c in CATALOG:
        x = dict(c)
        if c["id"] in loc:
            x["local_path"] = loc[c["id"]]["path"]
        out.append(x)
    return out


# ----------------------------------------------------------------------------
# Chạy / dừng llama-server
# ----------------------------------------------------------------------------
SERVER = {"proc": None, "state": "stopped", "model": None, "name": None, "msg": "", "port": None, "started": 0,
          "ctx": None}
_slock = threading.Lock()
_JOB = [None]


def _assign_job(proc):
    """Windows: gắn tiến trình vào Job để nó tự tắt khi app bị tắt đột ngột."""
    if not IS_WIN:
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        if _JOB[0] is None:
            job = k32.CreateJobObjectW(None, None)

            class BASIC(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class IOC(ctypes.Structure):
                _fields_ = [(n, ctypes.c_uint64) for n in ("a", "b", "c", "d", "e", "f")]

            class EXT(ctypes.Structure):
                _fields_ = [("Basic", BASIC), ("Io", IOC), ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]
            info = EXT()
            info.Basic.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
            k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
            _JOB[0] = job
        h = k32.OpenProcess(0x1F0FFF, False, proc.pid)
        k32.AssignProcessToJobObject(_JOB[0], h)
        k32.CloseHandle(h)
    except Exception:  # noqa
        pass


def _free_port(pref):
    import socket
    for p in (pref, 0):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            s.close()
    return pref


def _log_path():
    return os.path.join(engine_dir(), "server.log")


def log_tail(n=25):
    try:
        with open(_log_path(), "r", encoding="utf-8", errors="replace") as f:
            return f.read()[-6000:].splitlines()[-n:]
    except OSError:
        return []


def _ascii_path(p):
    """Windows: llama-server đọc tham số theo bảng mã ANSI nên đường dẫn có dấu (VD "Xưởng Truyện")
    có thể hỏng – đổi sang dạng tên ngắn 8.3 (không dấu) nếu có."""
    if not IS_WIN or p.isascii():
        return p
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(p, buf, 1024) and buf.value.isascii():
            return buf.value
    except Exception:  # noqa
        pass
    return p


def _alias(path, name):
    return name or re.sub(r"(-\d{5}-of-\d{5})?\.gguf$", "", os.path.basename(path))


def start_server(model_path, ctx=None, name=None):
    exe = _find_server_exe()
    if not exe:
        raise RuntimeError("Chưa cài bộ máy chạy model. Bấm “Cài bộ máy” trước.")
    if not os.path.exists(model_path):
        raise RuntimeError("Không thấy file model: " + model_path)
    s = storage.load_settings()
    ctx = int(ctx or s.get("engine_ctx") or 16384)
    stop_server()
    port = _free_port(int(s.get("engine_port") or 8091))
    if not name:
        for m in local_models():
            if os.path.realpath(m["path"]) == os.path.realpath(model_path):
                name = m["name"]
                break
    alias = _alias(model_path, name)
    args = [exe, "-m", _ascii_path(model_path), "--host", "127.0.0.1", "--port", str(port), "-c", str(ctx),
            "-np", "1", "--alias", alias, "--no-webui", "-ctk", "q8_0", "-ctv", "q8_0"]
    if s.get("no_think", True):
        args += ["--reasoning", "off"]
    with _slock:
        logf = open(_log_path(), "w", encoding="utf-8", errors="replace")
        proc = subprocess.Popen(args, cwd=os.path.dirname(exe), stdout=logf, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        _assign_job(proc)
        SERVER.update(proc=proc, state="loading", model=model_path, name=alias, port=port, ctx=ctx,
                      started=time.time(), msg="Đang nạp model vào GPU/RAM…", logf=logf)
    storage.save_settings({"engine_model": model_path, "engine_ctx": ctx, "provider": "builtin",
                           "base_url": f"http://127.0.0.1:{port}/v1", "model": alias, "api_key": ""})
    threading.Thread(target=_watch, args=(proc, port), daemon=True).start()
    return status()


def _watch(proc, port):
    while True:
        if SERVER["proc"] is not proc:
            return
        rc = proc.poll()
        if rc is not None:
            if SERVER["state"] != "stopped":
                SERVER["state"] = "error"
                tail = "\n".join(log_tail(8))
                hint = ""
                low = tail.lower()
                if "out of memory" in low or "failed to allocate" in low:
                    hint = " Thiếu bộ nhớ: hãy giảm Context hoặc chọn model nhỏ hơn."
                elif "unknown model architecture" in low or "unknown architecture" in low:
                    hint = " Bộ máy chưa hỗ trợ model này: bấm “Cập nhật bộ máy”."
                elif "failed to open" in low or "no such file" in low or "failed to load model" in low:
                    hint = (" Không mở được file model. Nếu thư mục app có dấu tiếng Việt, hãy chuyển app sang "
                            "thư mục không dấu (VD D:\\XuongTruyen) hoặc tải lại model.")
                elif "error while loading shared libraries" in low or "dll" in low:
                    hint = " Thiếu thư viện: thử cài lại bộ máy bản Vulkan."
                SERVER["msg"] = f"llama-server đã dừng (mã {rc}).{hint}"
            return
        if SERVER["state"] == "loading":
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                    if r.status == 200:
                        SERVER["state"] = "ready"
                        SERVER["msg"] = f"Sẵn sàng sau {int(time.time() - SERVER['started'])} giây"
            except Exception:  # noqa
                pass
        time.sleep(1)


def stop_server():
    with _slock:
        p = SERVER.get("proc")
        SERVER.update(state="stopped", msg="Đã dừng")
        SERVER["proc"] = None
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=8)
            except Exception:  # noqa
                try:
                    p.kill()
                except Exception:  # noqa
                    pass
        lf = SERVER.pop("logf", None)
        if lf:
            try:
                lf.close()
            except Exception:  # noqa
                pass


atexit.register(stop_server)


def status():
    return {
        "server": {k: SERVER.get(k) for k in ("state", "model", "name", "msg", "port", "ctx")},
        "engine": {k: v for k, v in engine_info().items() if k != "exe"},
        "tasks": task_list(),
    }


def autostart():
    s = storage.load_settings()
    if s.get("provider") != "builtin" or not s.get("engine_autostart", True):
        return
    m = s.get("engine_model")
    if m and os.path.exists(m) and engine_info()["installed"]:
        try:
            start_server(m, s.get("engine_ctx"))
        except Exception as e:  # noqa
            SERVER.update(state="error", msg=str(e))
