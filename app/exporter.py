"""Xuất truyện ra Word (.docx), EPUB và TXT."""
import html
import os
import re
import time
import uuid
import zipfile

from .prompts import RATING_LABELS


def safe_filename(name):
    name = re.sub(r'[\\/:*?"<>|]+', "", name or "truyen").strip() or "truyen"
    return name[:80]


def _paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n|\n", text or "") if p.strip()]


def _chapters(story, only_written):
    out = []
    for i, c in enumerate(story.get("chapters") or []):
        if only_written and not (c.get("content") or "").strip():
            continue
        out.append((i, c))
    return out


def export_txt(story, path, only_written=True, include_info=True):
    lines = [story.get("title", "").upper(), ""]
    if include_info:
        if story.get("genre"):
            lines.append("Thể loại: " + story["genre"])
        if story.get("logline"):
            lines.append("Giới thiệu: " + story["logline"])
        lines.append("")
    for i, c in _chapters(story, only_written):
        lines += ["", f"Chương {i + 1}: {c.get('title', '')}", ""]
        lines += [p + "\n" for p in _paragraphs(c.get("content"))]
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines).strip() + "\n")
    return path


def export_docx(story, path, only_written=True, include_info=True):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.shared import Pt, Cm

    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.2)
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(13)
    st.paragraph_format.space_after = Pt(6)
    st.paragraph_format.line_spacing = 1.3
    for hn in ("Title", "Heading 1"):
        doc.styles[hn].font.name = "Times New Roman"

    t = doc.add_paragraph(style="Title")
    t.add_run(story.get("title", ""))
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if include_info:
        for label, key in (("Thể loại", "genre"), ("Giới thiệu", "logline")):
            if story.get(key):
                p = doc.add_paragraph()
                p.add_run(label + ": ").bold = True
                p.add_run(story[key])
        p = doc.add_paragraph()
        p.add_run("Giới hạn nội dung: ").bold = True
        p.add_run(RATING_LABELS.get(story.get("rating", "all"), ""))

    first = True
    for i, c in _chapters(story, only_written):
        if not first or include_info:
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        first = False
        doc.add_heading(f"Chương {i + 1}: {c.get('title', '')}", level=1)
        for para in _paragraphs(c.get("content")):
            p = doc.add_paragraph(para)
            p.paragraph_format.first_line_indent = Cm(0.8)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    doc.save(path)
    return path


def export_epub(story, path, only_written=True, include_info=True):
    title = story.get("title", "Truyện")
    uid = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "xuongtruyen:" + story.get("id", title)))
    lang = "vi" if "Việt" in (story.get("language") or "Tiếng Việt") else "en"
    chs = _chapters(story, only_written)
    e = html.escape

    css = (
        "body{font-family:serif;line-height:1.6;margin:0 4%;}"
        "h1{text-align:center;margin:1.5em 0 1em;font-size:1.4em;}"
        "p{text-indent:1.5em;margin:0 0 .5em;text-align:justify;}"
        ".info p{text-indent:0}.title{text-align:center;font-size:2em;margin-top:30%;}"
    )

    def page(t, body):
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}" lang="{lang}"><head>'
            f'<meta charset="utf-8"/><title>{e(t)}</title><link rel="stylesheet" type="text/css" href="style.css"/>'
            f"</head><body>{body}</body></html>"
        )

    files = []  # (id, href, title, content)
    info = f'<p class="title">{e(title)}</p>'
    if include_info:
        info += '<div class="info">'
        if story.get("genre"):
            info += f"<p><b>Thể loại:</b> {e(story['genre'])}</p>"
        if story.get("logline"):
            info += f"<p><b>Giới thiệu:</b> {e(story['logline'])}</p>"
        info += "</div>"
    files.append(("titlepage", "titlepage.xhtml", title, page(title, info)))
    for n, (i, c) in enumerate(chs):
        ct = f"Chương {i + 1}: {c.get('title', '')}"
        body = f"<h1>{e(ct)}</h1>" + "".join(f"<p>{e(p)}</p>" for p in _paragraphs(c.get("content")))
        files.append((f"ch{n + 1}", f"ch{n + 1}.xhtml", ct, page(ct, body)))

    manifest = "".join(
        f'<item id="{fid}" href="{href}" media-type="application/xhtml+xml"/>' for fid, href, _, _ in files)
    spine = "".join(f'<itemref idref="{fid}"/>' for fid, _, _, _ in files)
    modified = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="bookid">{uid}</dc:identifier><dc:title>{e(title)}</dc:title>'
        f'<dc:language>{lang}</dc:language><dc:creator>Xưởng Truyện</dc:creator>'
        f'<meta property="dcterms:modified">{modified}</meta></metadata>'
        '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        f'<item id="css" href="style.css" media-type="text/css"/>{manifest}</manifest>'
        f'<spine toc="ncx">{spine}</spine></package>'
    )
    nav_items = "".join(f'<li><a href="{href}">{e(t)}</a></li>' for _, href, t, _ in files[1:])
    nav = (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
        f'<head><meta charset="utf-8"/><title>Mục lục</title></head><body>'
        f'<nav epub:type="toc"><h1>Mục lục</h1><ol>{nav_items}</ol></nav></body></html>'
    )
    points = "".join(
        f'<navPoint id="np{k}" playOrder="{k}"><navLabel><text>{e(t)}</text></navLabel><content src="{href}"/></navPoint>'
        for k, (_, href, t, _) in enumerate(files, start=1))
    ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f'<head><meta name="dtb:uid" content="{uid}"/></head><docTitle><text>{e(title)}</text></docTitle>'
        f"<navMap>{points}</navMap></ncx>"
    )
    container = (
        '<?xml version="1.0"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", css, compress_type=zipfile.ZIP_DEFLATED)
        for _, href, _, content in files:
            z.writestr("OEBPS/" + href, content, compress_type=zipfile.ZIP_DEFLATED)
    return path


EXPORTERS = {"docx": export_docx, "epub": export_epub, "txt": export_txt}


def export(story, fmt, folder, path=None, only_written=True, include_info=True):
    fmt = fmt.lower()
    if fmt not in EXPORTERS:
        raise ValueError("Định dạng không hỗ trợ: " + fmt)
    if not path:
        path = os.path.join(folder, safe_filename(story.get("title")) + "." + fmt)
    return EXPORTERS[fmt](story, path, only_written=only_written, include_info=include_info)
