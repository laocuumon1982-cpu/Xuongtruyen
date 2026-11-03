"""Gọi model local qua API kiểu OpenAI (LM Studio, Ollama, KoboldCpp, llama.cpp...)."""
import json
import re
import urllib.error
import urllib.request


class LLMError(Exception):
    pass


def _headers(settings):
    h = {"Content-Type": "application/json"}
    key = (settings.get("api_key") or "").strip()
    if key:
        h["Authorization"] = "Bearer " + key
    return h


def _base(settings):
    return (settings.get("base_url") or "").rstrip("/")


def list_models(settings, timeout=8):
    req = urllib.request.Request(_base(settings) + "/models", headers=_headers(settings))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.URLError as e:
        raise LLMError(f"Không kết nối được tới {_base(settings)} ({e.reason if hasattr(e, 'reason') else e}). "
                       "Hãy mở LM Studio/Ollama/KoboldCpp và bật server.")
    except Exception as e:  # noqa
        raise LLMError(f"Lỗi đọc danh sách model: {e}")
    items = data.get("data") or data.get("models") or []
    out = []
    for m in items:
        mid = m.get("id") or m.get("name") or m.get("model")
        if mid:
            out.append(mid)
    return out


class ThinkFilter:
    """Lọc bỏ phần <think>...</think> mà Qwen3 / model suy luận hay in ra."""

    def __init__(self):
        self.buf = ""
        self.in_think = False
        self.started = False

    def feed(self, s):
        self.buf += s
        out = []
        while self.buf:
            if self.in_think:
                i = self.buf.find("</think>")
                if i < 0:
                    # giữ lại phần đuôi có thể là đầu của "</think>"
                    self.buf = self.buf[-8:]
                    break
                self.buf = self.buf[i + 8:]
                self.in_think = False
                continue
            i = self.buf.find("<think>")
            if i < 0:
                # có thể đang giữa thẻ "<thi"
                j = self.buf.rfind("<")
                if j >= 0 and "<think>".startswith(self.buf[j:]) and len(self.buf) - j < 7:
                    out.append(self.buf[:j])
                    self.buf = self.buf[j:]
                else:
                    out.append(self.buf)
                    self.buf = ""
                break
            out.append(self.buf[:i])
            self.buf = self.buf[i + 7:]
            self.in_think = True
        text = "".join(out)
        if not self.started:
            text = text.lstrip()
            if text:
                self.started = True
        return text

    def flush(self):
        if self.in_think:
            return ""
        t, self.buf = self.buf, ""
        return t


def stream_chat(settings, messages, max_tokens=None, temperature=None, stop_flag=None):
    """Sinh văn bản dạng stream. Trả về generator các mẩu chữ (đã lọc <think>)."""
    msgs = [dict(m) for m in messages]
    if settings.get("no_think") and msgs and msgs[0]["role"] == "system":
        # Qwen3: tắt chế độ suy nghĩ để viết nhanh hơn
        msgs[0]["content"] = msgs[0]["content"] + "\n/no_think"
    body = {
        "model": settings.get("model") or "local-model",
        "messages": msgs,
        "stream": True,
        "temperature": float(settings.get("temperature", 0.85) if temperature is None else temperature),
        "top_p": float(settings.get("top_p", 0.95)),
        "max_tokens": int(max_tokens or settings.get("max_tokens", 4096)),
    }
    req = urllib.request.Request(
        _base(settings) + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=_headers(settings),
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=600)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise LLMError(f"Server model báo lỗi {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise LLMError(f"Không kết nối được tới {_base(settings)}: {getattr(e, 'reason', e)}. "
                       "Hãy mở LM Studio/Ollama/KoboldCpp, nạp model và bật server.")
    flt = ThinkFilter()
    try:
        for raw in resp:
            if stop_flag is not None and stop_flag():
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except ValueError:
                continue
            if obj.get("error"):
                raise LLMError(str(obj["error"]))
            ch = (obj.get("choices") or [{}])[0]
            delta = ch.get("delta") or {}
            piece = delta.get("content")
            if piece is None:
                piece = ch.get("text")
            if piece:
                out = flt.feed(piece)
                if out:
                    yield out
        tail = flt.flush()
        if tail:
            yield tail
    finally:
        try:
            resp.close()
        except Exception:  # noqa
            pass


def complete(settings, messages, **kw):
    return "".join(stream_chat(settings, messages, **kw)).strip()


def parse_json_loose(text):
    """Đọc JSON từ câu trả lời của model (có thể kèm ```json, chữ thừa, dấu phẩy thừa)."""
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    t = t.replace("```json", "```")
    m = re.search(r"```(.*?)```", t, flags=re.S)
    if m and "{" in m.group(1):
        t = m.group(1)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("Model không trả về JSON")
    t = t[a:b + 1]
    for attempt in range(3):
        try:
            return json.loads(t)
        except ValueError:
            if attempt == 0:
                t = re.sub(r",\s*([}\]])", r"\1", t)  # dấu phẩy thừa
            elif attempt == 1:
                t = t.replace("“", '"').replace("”", '"')
    return json.loads(t)
