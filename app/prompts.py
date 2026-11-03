"""Tạo prompt cho từng chức năng: lên dàn ý, viết chương, viết tiếp, sửa đoạn, chat, tóm tắt."""

RATING_LABELS = {
    "all": "Mọi lứa tuổi",
    "18": "18+",
    "nsfw": "NSFW (18+ có cảnh nóng)",
}

RATING_RULES = {
    "all": (
        "GIỚI HẠN NỘI DUNG: Mọi lứa tuổi. Không có cảnh tình dục hay gợi dục, không miêu tả bạo lực "
        "đẫm máu, không chửi thề nặng. Xung đột và cảm xúc vẫn có thể sâu sắc nhưng trình bày tinh tế."
    ),
    "18": (
        "GIỚI HẠN NỘI DUNG: 18+. Được phép bạo lực, chủ đề u tối, ngôn từ mạnh, căng thẳng tâm lý và "
        "các cảnh tình cảm, gợi cảm giữa người trưởng thành. Cảnh quan hệ tình dục chỉ ám chỉ hoặc "
        "chuyển cảnh, không miêu tả chi tiết."
    ),
    "nsfw": (
        "GIỚI HẠN NỘI DUNG: NSFW dành cho người lớn. Được phép viết cảnh tình dục rõ ràng, chi tiết, "
        "trần trụi giữa các nhân vật trưởng thành khi mạch truyện dẫn tới, cùng bạo lực và ngôn từ mạnh. "
        "Viết tự nhiên, gợi cảm, tập trung vào cảm xúc và cảm giác của nhân vật, không tự kiểm duyệt "
        "hay chèn lời bình đạo đức."
    ),
}

HARD_RULE = (
    "QUY TẮC BẮT BUỘC (áp dụng mọi chế độ): mọi nhân vật xuất hiện trong cảnh tình dục hoặc gợi dục đều là "
    "người trưởng thành từ 18 tuổi trở lên. Tuyệt đối không viết nội dung tình dục hay gợi dục liên quan "
    "đến trẻ vị thành niên dưới bất kỳ hình thức nào."
)


def system_writer(story):
    lang = story.get("language") or "Tiếng Việt"
    rating = story.get("rating") or "all"
    return (
        f"Bạn là một nhà văn chuyên nghiệp, viết tiểu thuyết bằng {lang} với văn phong giàu hình ảnh, "
        "lời thoại tự nhiên, nhịp truyện cuốn hút, nhân vật nhất quán. Bạn chỉ trả về đúng phần văn bản "
        "được yêu cầu, không mở đầu bằng lời dẫn, không giải thích, không dùng markdown.\n\n"
        f"{RATING_RULES.get(rating, RATING_RULES['all'])}\n{HARD_RULE}"
    )


def bible_text(story, with_outline=True):
    parts = [f"TÊN TRUYỆN: {story.get('title', '')}"]
    for key, label in (("genre", "Thể loại"), ("logline", "Tóm tắt ý tưởng"), ("style", "Giọng văn"),
                       ("pov", "Ngôi kể"), ("world", "Thế giới / bối cảnh"), ("notes", "Ghi chú của tác giả")):
        v = (story.get(key) or "").strip()
        if v:
            parts.append(f"{label}: {v}")
    chars = story.get("characters") or []
    if chars:
        lines = []
        for c in chars:
            bits = [c.get("name", "?")]
            if c.get("role"):
                bits.append(f"({c['role']})")
            if c.get("age"):
                bits.append(f"[{c['age']}]")
            desc = (c.get("desc") or "").strip()
            lines.append("- " + " ".join(bits) + (f": {desc}" if desc else ""))
        parts.append("NHÂN VẬT:\n" + "\n".join(lines))
    if with_outline:
        chs = story.get("chapters") or []
        if chs:
            lines = [f"{i + 1}. {c.get('title', '')}: {c.get('outline', '')}" for i, c in enumerate(chs)]
            parts.append("DÀN Ý CÁC CHƯƠNG:\n" + "\n".join(lines))
    return "\n\n".join(parts)


def _clip_tail(text, n):
    text = text or ""
    if len(text) <= n:
        return text
    cut = text[-n:]
    k = cut.find("\n")
    if 0 <= k < 400:
        cut = cut[k + 1:]
    return "…" + cut


def _clip_head(text, n):
    text = text or ""
    return text if len(text) <= n else text[:n] + "…"


def memory_text(story, upto, budget):
    """Tóm tắt các chương trước chương `upto` để AI nhớ mạch truyện dài.
    Các chương gần dùng tóm tắt đầy đủ, chương xa thì rút gọn nếu vượt ngân sách."""
    chs = (story.get("chapters") or [])[:upto]
    items = []
    for i, c in enumerate(chs):
        s = (c.get("summary") or "").strip() or (c.get("outline") or "").strip()
        items.append((i, c.get("title", ""), s))
    if not items:
        return ""

    def render(full_from):
        out = []
        for i, title, s in items:
            if i >= full_from:
                out.append(f"Chương {i + 1} – {title}: {s}")
            else:
                out.append(f"Chương {i + 1} – {title}: {_clip_head(s, 160)}")
        return "\n".join(out)

    full_from = 0
    txt = render(full_from)
    while len(txt) > budget and full_from < len(items):
        full_from += 1
        txt = render(full_from)
    if len(txt) > budget:
        txt = _clip_tail(txt, budget)
    return "DIỄN BIẾN ĐÃ XẢY RA (tóm tắt các chương trước):\n" + txt


def _context_block(story, idx, settings):
    budget = int(settings.get("context_chars", 24000))
    bible = bible_text(story)
    if len(bible) > budget * 0.45:
        bible = _clip_head(bible, int(budget * 0.45))
    mem = memory_text(story, idx, int(budget * 0.35))
    chs = story.get("chapters") or []
    prev_tail = ""
    if idx > 0 and idx - 1 < len(chs):
        pc = chs[idx - 1].get("content") or ""
        if pc.strip():
            prev_tail = "ĐOẠN CUỐI CHƯƠNG TRƯỚC (để nối mạch):\n" + _clip_tail(pc, int(budget * 0.15))
    return "\n\n".join(x for x in (bible, mem, prev_tail) if x)


def plan_messages(idea, draft, rating, n_chapters, language, genre_hint):
    src = ""
    if idea.strip():
        src += f"Ý TƯỞNG CỦA TÁC GIẢ:\n{idea.strip()}\n\n"
    if draft.strip():
        src += f"BẢN NHÁP TÁC GIẢ ĐÃ VIẾT (dựa vào đây để xây dựng truyện, giữ nguyên tên và sự kiện):\n{draft.strip()[:12000]}\n\n"
    if genre_hint.strip():
        src += f"Thể loại mong muốn: {genre_hint.strip()}\n"
    sys = (
        f"Bạn là biên tập viên và nhà văn giàu kinh nghiệm. Bạn thiết kế truyện bằng {language}. "
        "Bạn CHỈ trả về một khối JSON hợp lệ, không thêm bất kỳ chữ nào khác.\n"
        f"{RATING_RULES.get(rating, RATING_RULES['all'])}\n{HARD_RULE}"
    )
    user = (
        f"{src}\nHãy phát triển thành một bộ truyện hoàn chỉnh gồm {n_chapters} chương. Trả về JSON đúng cấu trúc:\n"
        "{\n"
        '  "title": "tên truyện hấp dẫn",\n'
        '  "genre": "thể loại",\n'
        '  "logline": "tóm tắt ý tưởng 2-3 câu",\n'
        '  "style": "mô tả giọng văn nên dùng",\n'
        '  "pov": "ngôi kể",\n'
        '  "world": "thế giới, bối cảnh, quy tắc, địa danh quan trọng (1-2 đoạn)",\n'
        '  "characters": [ {"name": "", "role": "vai trò", "age": "tuổi", "desc": "ngoại hình, tính cách, động cơ, bí mật"} ],\n'
        f'  "chapters": [ {{"title": "tên chương", "outline": "dàn ý chi tiết 3-5 câu: sự kiện chính, xung đột, kết chương"}} ]  // đúng {n_chapters} chương\n'
        "}\n"
        "Nhân vật 3-8 người, dàn ý có cao trào và cái kết rõ ràng. Viết tất cả bằng " + language + "."
    )
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def extend_outline_messages(story, count):
    sys = system_writer(story).replace("không dùng markdown.", "không dùng markdown. Lần này bạn CHỈ trả về JSON.")
    user = (
        bible_text(story) + "\n\n" + memory_text(story, len(story.get("chapters") or []), 6000) +
        f"\n\nHãy viết thêm dàn ý cho {count} chương tiếp theo, nối tiếp tự nhiên. Trả về JSON:\n"
        '{"chapters": [{"title": "tên chương", "outline": "dàn ý 3-5 câu"}]}'
    )
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def write_chapter_messages(story, idx, settings, extra=""):
    ch = story["chapters"][idx]
    words = int(settings.get("chapter_words", 2500))
    nxt = ""
    chs = story.get("chapters") or []
    if idx + 1 < len(chs):
        nxt = f"\n(Chương sau sẽ là: {chs[idx + 1].get('title', '')} – {chs[idx + 1].get('outline', '')}. Đừng viết trước nội dung chương sau.)"
    user = (
        _context_block(story, idx, settings) +
        f"\n\n=== NHIỆM VỤ ===\nViết trọn CHƯƠNG {idx + 1}: \"{ch.get('title', '')}\".\n"
        f"Dàn ý chương: {ch.get('outline', '')}{nxt}\n"
        f"Độ dài khoảng {words} từ. Mở đầu ngay vào nội dung (không ghi tiêu đề chương), có miêu tả, nội tâm, "
        "đối thoại; kết chương tạo móc câu cho chương sau."
        + (f"\nYêu cầu thêm của tác giả: {extra}" if extra.strip() else "")
    )
    return [{"role": "system", "content": system_writer(story)}, {"role": "user", "content": user}]


def continue_messages(story, idx, before, after, settings, extra=""):
    ch = story["chapters"][idx]
    budget = int(settings.get("context_chars", 24000))
    user = (
        _context_block(story, idx, settings) +
        f"\n\n=== CHƯƠNG {idx + 1}: {ch.get('title', '')} ===\nDàn ý chương: {ch.get('outline', '')}\n\n"
        f"NỘI DUNG ĐÃ VIẾT ĐẾN HIỆN TẠI:\n{_clip_tail(before, int(budget * 0.3))}\n"
        + (f"\n(Phần văn bản phía sau vị trí cần viết tiếp, để nối cho khớp:\n{_clip_head(after, 1500)})\n" if after.strip() else "")
        + "\n=== NHIỆM VỤ ===\nViết tiếp ngay từ chỗ dừng (khoảng 400-700 từ), liền mạch về giọng văn và sự kiện, "
        "bám theo dàn ý chương. Không lặp lại đoạn đã có, không tóm tắt, chỉ trả về đoạn viết tiếp."
        + (f"\nYêu cầu thêm: {extra}" if extra.strip() else "")
    )
    return [{"role": "system", "content": system_writer(story)}, {"role": "user", "content": user}]


EDIT_TASKS = {
    "rewrite": "Viết lại đoạn được chọn cho hay hơn: câu chữ mượt, giàu hình ảnh, giữ nguyên ý và sự kiện, độ dài tương đương.",
    "expand": "Mở rộng đoạn được chọn dài gấp khoảng 2-3 lần: thêm chi tiết miêu tả, cảm giác, nội tâm, hành động, đối thoại; giữ đúng sự kiện.",
    "shorten": "Rút gọn đoạn được chọn còn khoảng một nửa, giữ ý chính và nhịp truyện.",
    "tone": "Viết lại đoạn được chọn theo giọng văn: {tone}. Giữ nguyên sự kiện.",
    "custom": "Sửa đoạn được chọn theo yêu cầu: {instruction}",
}


def edit_messages(story, idx, selected, before, after, mode, tone="", instruction="", settings=None):
    settings = settings or {}
    task = EDIT_TASKS.get(mode, EDIT_TASKS["rewrite"]).format(tone=tone or "trang trọng", instruction=instruction)
    ch = (story.get("chapters") or [{}])[idx] if idx is not None and idx < len(story.get("chapters") or []) else {}
    user = (
        bible_text(story, with_outline=False)[:6000] +
        f"\n\n=== ĐANG Ở CHƯƠNG: {ch.get('title', '')} ===\n"
        f"Văn bản ngay trước đoạn chọn:\n{_clip_tail(before, 2000)}\n\n"
        f"<<ĐOẠN ĐƯỢC CHỌN>>\n{selected}\n<</ĐOẠN ĐƯỢC CHỌN>>\n\n"
        f"Văn bản ngay sau đoạn chọn:\n{_clip_head(after, 1200)}\n\n"
        f"=== NHIỆM VỤ ===\n{task}\nChỉ trả về đoạn văn thay thế cho ĐOẠN ĐƯỢC CHỌN, không kèm ký hiệu hay lời giải thích."
    )
    return [{"role": "system", "content": system_writer(story)}, {"role": "user", "content": user}]


def summarize_messages(story, idx):
    ch = story["chapters"][idx]
    sys = (
        "Bạn là trợ lý biên tập. Hãy tóm tắt chương truyện thật súc tích nhưng đủ thông tin để viết tiếp: "
        "sự kiện chính, thay đổi quan hệ/trạng thái nhân vật, bí mật được hé lộ, đồ vật/địa điểm quan trọng, "
        "tình huống ở cuối chương. Viết 5-10 câu bằng " + (story.get("language") or "Tiếng Việt") +
        ", không markdown, không bình luận."
    )
    content = ch.get("content") or ""
    if len(content) > 30000:
        content = content[:15000] + "\n…\n" + content[-15000:]
    user = f"Chương {idx + 1}: {ch.get('title', '')}\n\n{content}"
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def chat_messages(story, history, settings):
    budget = int(settings.get("context_chars", 24000))
    chs = story.get("chapters") or []
    sys = (
        "Bạn là trợ lý sáng tác, cùng tác giả bàn bạc về truyện: góp ý cốt truyện, nhân vật, xung đột, "
        "plot twist, sửa lỗi logic, gợi ý tình tiết. Trả lời thân thiện, cụ thể, bằng tiếng Việt.\n"
        f"{RATING_RULES.get(story.get('rating') or 'all')}\n{HARD_RULE}\n\n"
        "THÔNG TIN TRUYỆN:\n" + bible_text(story)[: int(budget * 0.5)] + "\n\n" +
        memory_text(story, len(chs), int(budget * 0.3))
    )
    msgs = [{"role": "system", "content": sys}]
    total = 0
    tail = []
    for m in reversed(history[-30:]):
        total += len(m.get("content", ""))
        if total > budget * 0.4 and tail:
            break
        tail.append({"role": m["role"], "content": m["content"]})
    msgs.extend(reversed(tail))
    return msgs
