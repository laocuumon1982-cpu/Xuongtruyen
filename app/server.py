"""Máy chủ nội bộ (127.0.0.1) phục vụ giao diện và các chức năng AI."""
import base64
import hashlib
import io
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import engine, exporter, llm, paths, prompts, storage, updater
from .version import APP_NAME, APP_VERSION, GITHUB_REPO

WINDOW = None          # cửa sổ pywebview (nếu có) – dùng cho hộp thoại lưu file
LAST_PING = [0.0]
_STOPS = set()
_UPDATE = {}


def text_hash(s):
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:16]


class ClientGone(Exception):
    pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "XuongTruyen/" + APP_VERSION

    def log_message(self, fmt, *args):  # im lặng
        pass

    # ---------- tiện ích ----------
    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _stream_start(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def _emit(self, **ev):
        try:
            self.wfile.write((json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            raise ClientGone()

    # ---------- GET ----------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p = u.path
        try:
            if p == "/api/info":
                return self._json({"name": APP_NAME, "version": APP_VERSION, "repo": GITHUB_REPO,
                                   "data_dir": paths.data_dir(), "frozen": bool(getattr(sys, "frozen", False)),
                                   "native_window": WINDOW is not None,
                                   "ratings": prompts.RATING_LABELS})
            if p == "/api/ping":
                LAST_PING[0] = time.time()
                return self._json({"ok": True})
            if p == "/api/settings":
                return self._json({"settings": storage.load_settings(), "presets": storage.PROVIDER_PRESETS})
            if p == "/api/models":
                st = storage.load_settings()
                if st.get("provider") == "builtin" and engine.SERVER["state"] != "ready":
                    msg = {"loading": "Model đang được nạp, đợi vài giây rồi bấm lại."}.get(
                        engine.SERVER["state"], "Chưa chạy model nào. Đóng cài đặt, bấm nút 🧠 trên thanh trên cùng để tải và chạy model.")
                    return self._json({"error": msg, "models": []})
                try:
                    return self._json({"models": llm.list_models(storage.load_settings())})
                except llm.LLMError as e:
                    return self._json({"error": str(e), "models": []})
            if p == "/api/stories":
                return self._json({"stories": storage.list_stories()})
            if p.startswith("/api/stories/"):
                st = storage.get_story(p.rsplit("/", 1)[1])
                return self._json(st) if st else self._json({"error": "Không tìm thấy truyện"}, 404)
            if p == "/api/engine/status":
                st = engine.status()
                if "gpu" in urllib.parse.parse_qs(u.query):
                    st["gpu"] = engine.gpu_info()
                st["models_dir"] = engine.models_dir()
                return self._json(st)
            if p == "/api/engine/catalog":
                return self._json({"catalog": engine.catalog(), "local": engine.local_models()})
            if p == "/api/update/check":
                try:
                    return self._json(updater.check())
                except Exception as e:  # noqa
                    return self._json({"error": f"Không kiểm tra được cập nhật: {e}", "current": APP_VERSION,
                                       "page": updater.RELEASES_PAGE})
            return self._static(p)
        except ClientGone:
            pass
        except Exception as e:  # noqa
            traceback.print_exc()
            self._json({"error": str(e)}, 500)

    def _static(self, p):
        if p in ("", "/"):
            p = "/index.html"
        root = os.path.join(paths.resource_dir(), "web")
        fp = os.path.normpath(os.path.join(root, p.lstrip("/")))
        if not fp.startswith(os.path.normpath(root)) or not os.path.isfile(fp):
            self.send_error(404)
            return
        with open(fp, "rb") as f:
            data = f.read()
        ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ---------- DELETE ----------
    def do_DELETE(self):
        p = urllib.parse.urlparse(self.path).path
        if p.startswith("/api/stories/"):
            storage.delete_story(p.rsplit("/", 1)[1])
            return self._json({"ok": True})
        self.send_error(404)

    # ---------- POST ----------
    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        try:
            body = self._body()
            if p == "/api/settings":
                return self._json({"settings": storage.save_settings(body)})
            if p == "/api/stories":
                body.pop("id", None)
                return self._json(storage.save_story(storage.new_story(**body)))
            if p == "/api/stop":
                _STOPS.add(body.get("job"))
                return self._json({"ok": True})
            if p == "/api/export":
                return self._export(body)
            if p == "/api/open":
                return self._open(body.get("path") or paths.exports_dir())
            if p == "/api/open_url":
                url = body.get("url") or ""
                if url.startswith("https://"):
                    import webbrowser
                    webbrowser.open(url)
                return self._json({"ok": True})
            if p == "/api/extract_text":
                return self._extract(body)
            if p == "/api/update/download":
                return self._update_download(body)
            if p == "/api/update/apply":
                if not _UPDATE.get("zip"):
                    return self._json({"error": "Chưa tải bản cập nhật"}, 400)
                self._json({"ok": True})
                threading.Timer(0.8, lambda: updater.apply_and_restart(_UPDATE["dir"], _UPDATE["zip"])).start()
                return None
            if p.startswith("/api/engine/"):
                return self._engine(p.rsplit("/", 1)[1], body)
            if p.startswith("/api/ai/"):
                return self._ai(p.rsplit("/", 1)[1], body)
            self.send_error(404)
        except ClientGone:
            pass
        except Exception as e:  # noqa
            traceback.print_exc()
            try:
                self._json({"error": str(e)}, 500)
            except Exception:  # noqa
                pass

    def do_PUT(self):
        p = urllib.parse.urlparse(self.path).path
        if p.startswith("/api/stories/"):
            st = self._body()
            st["id"] = p.rsplit("/", 1)[1]
            return self._json({"ok": True, "updated": storage.save_story(st)["updated"]})
        self.send_error(404)

    # ---------- bộ máy model tích hợp ----------
    def _engine(self, act, body):
        try:
            if act == "install":
                return self._json({"task": engine.install_engine(body.get("backend"))["id"]})
            if act == "download":
                cid = body.get("id")
                c = next((x for x in engine.CATALOG if x["id"] == cid), None)
                repo = c["repo"] if c else (body.get("repo") or "").strip()
                quant = (c["quant"] if c else (body.get("quant") or "Q4_K_M")).strip()
                if not repo or "/" not in repo:
                    return self._json({"error": "Nhập tên repo dạng tác-giả/tên-model"}, 400)
                if repo.startswith("https://"):
                    repo = "/".join(repo.split("huggingface.co/", 1)[-1].split("/")[:2])
                t = engine.download_model(repo, quant, name=(c or {}).get("name") or repo.split("/")[-1],
                                          start_after=bool(body.get("start")), catalog_id=cid)
                return self._json({"task": t["id"]})
            if act == "quick":
                c = next((x for x in engine.CATALOG if x["id"] == body.get("id")), engine.CATALOG[0])
                if not engine.engine_info()["installed"]:
                    engine.install_engine()
                loc = next((m for m in engine.local_models() if m.get("catalog_id") == c["id"]), None)
                if loc:
                    def go():
                        et = next((t for t in engine.TASKS.values() if t["kind"] == "engine" and t["state"] == "running"), None)
                        while et and et["state"] == "running":
                            time.sleep(1)
                        engine.start_server(loc["path"], name=c["name"])
                    threading.Thread(target=go, daemon=True).start()
                    return self._json({"ok": True})
                t = engine.download_model(c["repo"], c["quant"], name=c["name"], start_after=True, catalog_id=c["id"])
                return self._json({"task": t["id"]})
            if act == "cancel":
                engine.cancel_task(body.get("task"))
                return self._json({"ok": True})
            if act == "start":
                return self._json(engine.start_server(body["path"], body.get("ctx"), body.get("name")))
            if act == "stop":
                engine.stop_server()
                return self._json(engine.status())
            if act == "delete_model":
                engine.delete_model(body["path"])
                return self._json({"ok": True})
            if act == "install_files":
                files = body.get("files") or []
                if not files:
                    if WINDOW is None:
                        return self._json({"error": "Không mở được hộp thoại chọn file."})
                    import webview
                    res = WINDOW.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True,
                                                    file_types=("Gói llama.cpp (*.zip)", "Tất cả (*.*)"))
                    if not res:
                        return self._json({"cancelled": True})
                    files = list(res)
                return self._json({"engine": engine.install_engine_from_files(files)})
            if act == "pick_folder":
                if WINDOW is None:
                    return self._json({"error": "Hãy nhập đường dẫn thư mục thủ công."})
                import webview
                res = WINDOW.create_file_dialog(webview.FOLDER_DIALOG)
                if not res:
                    return self._json({"cancelled": True})
                return self._json({"path": res if isinstance(res, str) else res[0]})
            if act == "add_folder":
                d = (body.get("path") or "").strip()
                if not os.path.isdir(d):
                    return self._json({"error": "Thư mục không tồn tại"}, 400)
                s = storage.load_settings()
                dirs = [x for x in (s.get("extra_model_dirs") or []) if x != d] + [d]
                storage.save_settings({"extra_model_dirs": dirs})
                return self._json({"ok": True})
            if act == "remove_folder":
                s = storage.load_settings()
                storage.save_settings({"extra_model_dirs": [x for x in (s.get("extra_model_dirs") or []) if x != body.get("path")]})
                return self._json({"ok": True})
            return self._json({"error": "Không rõ thao tác"}, 404)
        except Exception as e:  # noqa
            return self._json({"error": str(e)}, 400)

    # ---------- xuất file ----------
    def _export(self, body):
        st = storage.get_story(body.get("id", ""))
        if not st:
            return self._json({"error": "Không tìm thấy truyện"}, 404)
        fmt = body.get("fmt", "docx")
        fname = exporter.safe_filename(st.get("title")) + "." + fmt
        path = None
        if body.get("ask") and WINDOW is not None:
            try:
                import webview
                res = WINDOW.create_file_dialog(webview.SAVE_DIALOG, directory=paths.exports_dir(),
                                                save_filename=fname)
                if not res:
                    return self._json({"cancelled": True})
                path = res if isinstance(res, str) else res[0]
                if not path.lower().endswith("." + fmt):
                    path += "." + fmt
            except Exception:  # noqa
                path = None
        out = exporter.export(st, fmt, paths.exports_dir(), path=path,
                              only_written=body.get("only_written", True),
                              include_info=body.get("include_info", True))
        return self._json({"path": out})

    def _open(self, path):
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        try:
            if os.name == "nt":
                if os.path.isfile(path):
                    subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
                else:
                    os.startfile(folder)  # noqa
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:  # noqa
            return self._json({"error": str(e)})
        return self._json({"ok": True})

    def _extract(self, body):
        name = (body.get("name") or "").lower()
        raw = base64.b64decode(body.get("b64") or "")
        if name.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(raw))
            text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        else:
            for enc in ("utf-8-sig", "utf-16", "cp1258", "latin-1"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
        return self._json({"text": text})

    def _update_download(self, body):
        self._stream_start()
        url = body.get("url")
        last = [0.0]

        def prog(done, total):
            if time.time() - last[0] > 0.25 or done == total:
                last[0] = time.time()
                self._emit(t="progress", done=done, total=total)

        try:
            d, z = updater.download(url, prog)
            _UPDATE.update(dir=d, zip=z)
            self._emit(t="done")
        except ClientGone:
            raise
        except Exception as e:  # noqa
            self._emit(t="error", d=f"Tải bản cập nhật lỗi: {e}")

    # ---------- AI ----------
    def _ai(self, task, body):
        settings = storage.load_settings()
        job = body.get("job") or ""
        stop = lambda: job in _STOPS  # noqa
        self._stream_start()

        def run(messages, **kw):
            out = []
            for piece in llm.stream_chat(settings, messages, stop_flag=stop, **kw):
                out.append(piece)
                self._emit(t="tok", d=piece)
            return "".join(out)

        try:
            story = body.get("story") or {}
            if task == "plan":
                msgs = prompts.plan_messages(body.get("idea", ""), body.get("draft", ""), body.get("rating", "all"),
                                             int(body.get("chapters", 12)), body.get("language", "Tiếng Việt"),
                                             body.get("genre", ""))
                text = run(msgs, max_tokens=max(4096, int(settings.get("max_tokens", 4096))), temperature=0.8)
                try:
                    self._emit(t="json", d=llm.parse_json_loose(text))
                except ValueError as e:
                    self._emit(t="error", d=f"Model trả về dàn ý không đúng định dạng JSON ({e}). Hãy bấm thử lại "
                                            "hoặc dùng model lớn hơn.", raw=text)
            elif task == "extend_outline":
                text = run(prompts.extend_outline_messages(story, int(body.get("count", 5))), temperature=0.8)
                try:
                    self._emit(t="json", d=llm.parse_json_loose(text))
                except ValueError as e:
                    self._emit(t="error", d=f"Không đọc được dàn ý ({e}). Thử lại nhé.", raw=text)
            elif task == "summaries":
                self._summaries(settings, story, int(body.get("upto", 0)), stop)
            elif task == "write_chapter":
                idx = int(body["index"])
                self._summaries(settings, story, idx, stop)
                run(prompts.write_chapter_messages(story, idx, settings, body.get("extra", "")))
            elif task == "continue":
                idx = int(body["index"])
                self._summaries(settings, story, idx, stop)
                run(prompts.continue_messages(story, idx, body.get("before", ""), body.get("after", ""), settings,
                                              body.get("extra", "")), max_tokens=min(2048, int(settings.get("max_tokens", 4096))))
            elif task == "edit":
                idx = body.get("index")
                run(prompts.edit_messages(story, int(idx) if idx is not None else 0, body.get("selected", ""),
                                          body.get("before", ""), body.get("after", ""), body.get("mode", "rewrite"),
                                          body.get("tone", ""), body.get("instruction", ""), settings))
            elif task == "chat":
                run(prompts.chat_messages(story, body.get("messages", []), settings), temperature=0.7)
            else:
                self._emit(t="error", d="Chức năng không tồn tại: " + task)
                return
            self._emit(t="end", stopped=stop())
        except llm.LLMError as e:
            msg = str(e)
            if settings.get("provider") == "builtin" and "kết nối" in msg:
                st = engine.SERVER["state"]
                msg = ("Model đang được nạp, đợi vài giây rồi thử lại nhé." if st == "loading" else
                       "Chưa có model nào đang chạy. Bấm nút 🧠 Model AI ở thanh trên để tải và chạy model.")
            self._emit(t="error", d=msg)
        except ClientGone:
            pass
        except Exception as e:  # noqa
            traceback.print_exc()
            try:
                self._emit(t="error", d=f"Lỗi: {e}")
            except ClientGone:
                pass
        finally:
            _STOPS.discard(job)

    def _summaries(self, settings, story, upto, stop):
        """Tự tóm tắt các chương cũ (đã viết, chưa có tóm tắt hoặc đã sửa sau lần tóm tắt trước)."""
        chs = story.get("chapters") or []
        todo = []
        for i, c in enumerate(chs[:upto]):
            content = (c.get("content") or "").strip()
            if content and (not c.get("summary") or c.get("summary_hash") != text_hash(content)):
                todo.append(i)
        for n, i in enumerate(todo):
            if stop():
                return
            self._emit(t="status", d=f"Đang tóm tắt chương {i + 1} để AI nhớ mạch truyện ({n + 1}/{len(todo)})…")
            s = llm.complete(settings, prompts.summarize_messages(story, i), max_tokens=700, temperature=0.3,
                             stop_flag=stop)
            h = text_hash((chs[i].get("content") or "").strip())
            chs[i]["summary"] = s
            chs[i]["summary_hash"] = h
            self._emit(t="summary", i=i, d=s, h=h)
        if todo:
            self._emit(t="status", d="Đang viết…")


def make_server(port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    return srv
