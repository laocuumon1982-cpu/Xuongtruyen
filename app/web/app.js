/* Xưởng Truyện – giao diện */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const uid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
const words = t => ((t || "").trim().match(/\S+/g) || []).length;

const TONES = [
  "Hài hước, dí dỏm", "U tối, căng thẳng", "Lãng mạn, bay bổng", "Cổ phong, kiếm hiệp",
  "Hiện đại, đời thường", "Thơ mộng, giàu hình ảnh", "Lạnh lùng, tối giản", "Kịch tính, dồn dập",
  "Trang trọng, văn chương", "Gợi cảm, quyến rũ"
];
const RATING_LABEL = { all: "Mọi lứa tuổi", "18": "18+", nsfw: "NSFW" };

async function api(path, opts = {}) {
  const o = { method: opts.method || (opts.body ? "POST" : "GET"), headers: {} };
  if (opts.body !== undefined) { o.body = JSON.stringify(opts.body); o.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, o);
  return r.json();
}

function toast(msg, err = false, ms = 3500, html = false) {
  const t = $("#toast");
  t[html ? "innerHTML" : "textContent"] = msg;
  t.className = "toast" + (err ? " err" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), ms);
}

const App = {
  story: null, pane: "overview", settings: {}, presets: {}, info: {}, stories: [],
  cur: null, undo: {}, saveTimer: null, ideaMode: "idea", chatOpen: true,

  /* ================== khởi động ================== */
  async init() {
    this.info = await api("/api/info");
    const s = await api("/api/settings");
    this.settings = s.settings; this.presets = s.presets;
    this.applyUi();
    this.bindStatic();
    await this.loadLibrary();
    this.refreshModel();
    setInterval(() => fetch("/api/ping").catch(() => {}), 10000);
    fetch("/api/ping");
    if (this.settings.check_update_on_start) this.checkUpdateQuiet();
  },

  applyUi() {
    document.documentElement.dataset.theme = this.settings.ui_theme || "dark";
    document.documentElement.style.setProperty("--edfs", (this.settings.font_size || 18) + "px");
  },

  bindStatic() {
    $$("#ideaMode button").forEach(b => b.onclick = () => {
      $$("#ideaMode button").forEach(x => x.classList.toggle("on", x === b));
      this.ideaMode = b.dataset.mode;
      $("#draftTools").classList.toggle("hidden", this.ideaMode !== "draft");
      $("#ideaText").placeholder = this.ideaMode === "draft"
        ? "Dán bản nháp của bạn vào đây (một chương, vài trang, hay cả truyện dang dở). AI sẽ đọc và dựng tên truyện, nhân vật, thế giới, dàn ý nối tiếp…"
        : "Ví dụ: Một cô thợ đồng hồ ở Hội An phát hiện chiếc đồng hồ của ông nội có thể quay ngược 7 phút, và mỗi lần dùng, ai đó trong thành phố lại quên mất cô…";
    });
    $("#draftFile").onchange = e => this.loadDraftFile(e.target.files[0]);
    $("#ideaText").addEventListener("keydown", e => { if (e.key === "Enter" && e.ctrlKey) this.plan(); });
    $$(".side-nav button").forEach(b => b.onclick = () => this.show(b.dataset.pane));
    $("#chatText").addEventListener("keydown", e => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); this.sendChat(); }
    });
    // menu bôi đen
    $$("#selMenu [data-act]").forEach(b => b.onmousedown = e => { e.preventDefault(); this.selAction(b.dataset.act); });
    $("#toneList").innerHTML = TONES.map(t => `<button data-tone="${esc(t)}">${esc(t)}</button>`).join("");
    $$("#toneList button").forEach(b => b.onmousedown = e => { e.preventDefault(); this.startEdit("tone", { tone: b.dataset.tone }); });
    $("#editReplace").onclick = () => this.applyEdit("replace");
    $("#editInsert").onclick = () => this.applyEdit("insert");
    $("#editRetry").onclick = () => this.startEdit(this.editReq.mode, this.editReq.opt, true);
    $("#editCancel").onclick = () => { this.stop(); this.hideEdit(); };
    document.addEventListener("mousedown", e => {
      if (!e.target.closest("#selMenu")) this.hideSel();
    });
    document.addEventListener("keydown", e => {
      if (e.key === "Escape") { this.hideSel(); if (!$("#modalBg").classList.contains("hidden")) this.closeModal(); }
      if (e.key === "s" && e.ctrlKey) { e.preventDefault(); this.saveNow(); }
    });
    window.addEventListener("beforeunload", () => this.saveNow(true));
  },

  /* ================== model ================== */
  async refreshModel() {
    const dot = $("#modelDot"), name = $("#modelName");
    name.textContent = "Đang kiểm tra model…"; dot.className = "dot";
    const r = await api("/api/models").catch(() => ({ error: "lỗi" }));
    if (r.error || !r.models) {
      dot.className = "dot bad"; name.textContent = "Chưa kết nối model – bấm để cài đặt";
      return false;
    }
    dot.className = "dot ok";
    const m = this.settings.model || r.models[0] || "model";
    name.textContent = m;
    return true;
  },

  /* ================== stream AI ================== */
  async ai(task, body, h = {}) {
    if (this.cur) { toast("AI đang bận, bấm ⏹ Dừng trước đã."); return { busy: true }; }
    const job = uid(), ctl = new AbortController();
    this.cur = { job, ctl };
    this.setBusy(true);
    const res = { text: "", json: null, error: null, raw: null, stopped: false };
    try {
      const r = await fetch("/api/ai/" + task, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, job }), signal: ctl.signal
      });
      const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let k;
        while ((k = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, k); buf = buf.slice(k + 1);
          if (!line.trim()) continue;
          let ev; try { ev = JSON.parse(line); } catch { continue; }
          if (ev.t === "tok") { res.text += ev.d; h.onTok && h.onTok(ev.d, res.text); }
          else if (ev.t === "status") h.onStatus && h.onStatus(ev.d);
          else if (ev.t === "summary") this.applySummary(ev.i, ev.d, ev.h);
          else if (ev.t === "json") res.json = ev.d;
          else if (ev.t === "error") { res.error = ev.d; res.raw = ev.raw; }
          else if (ev.t === "end") res.stopped = !!ev.stopped;
        }
      }
    } catch (e) {
      if (e.name === "AbortError") res.stopped = true; else res.error = "Mất kết nối: " + e.message;
    } finally {
      this.cur = null; this.setBusy(false);
    }
    if (res.error) toast(res.error, true, 7000);
    return res;
  },

  stop() {
    if (!this.cur) return;
    fetch("/api/stop", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ job: this.cur.job }) });
    try { this.cur.ctl.abort(); } catch {}
  },

  setBusy(b) {
    document.body.classList.toggle("busy", b);
    $$(".needs-idle").forEach(x => x.disabled = b);
    $$(".needs-busy").forEach(x => x.classList.toggle("hidden", !b));
    const wrap = $(".ed-wrap"); if (wrap) wrap.classList.toggle("writing", b);
    $("#btnPlan").disabled = b; $("#chatSend").disabled = b;
  },

  applySummary(i, d, h) {
    const c = this.story && this.story.chapters[i];
    if (!c) return;
    c.summary = d; c.summary_hash = h;
    this.scheduleSave();
    if (this.pane === "ch:" + i) { const s = $("#sumText"); if (s) s.value = d; }
  },

  /* ================== thư viện ================== */
  async loadLibrary() {
    const r = await api("/api/stories");
    this.stories = r.stories || [];
    this.renderLibrary();
  },

  renderLibrary() {
    const q = ($("#libSearch").value || "").toLowerCase();
    const list = this.stories.filter(s => !q || (s.title + " " + s.logline + " " + s.genre).toLowerCase().includes(q));
    const g = $("#storyGrid");
    if (!list.length) {
      g.innerHTML = `<div class="empty">${this.stories.length ? "Không có truyện khớp." : "Chưa có truyện nào. Ném một ý tưởng vào ô phía trên để bắt đầu ✨"}</div>`;
      return;
    }
    g.innerHTML = list.map(s => `
      <div class="book" data-id="${s.id}">
        <button class="mini del" title="Xoá truyện" data-del="${s.id}">🗑</button>
        <h3>${esc(s.title)}</h3>
        <p>${esc(s.logline || "Chưa có giới thiệu")}</p>
        <div class="meta">
          ${s.genre ? `<span class="tag">${esc(s.genre)}</span>` : ""}
          <span class="tag r-${s.rating}">${RATING_LABEL[s.rating] || ""}</span>
          <span>${s.written}/${s.chapters} chương · ${s.words.toLocaleString("vi")} từ</span>
        </div>
      </div>`).join("");
    $$(".book", g).forEach(el => el.onclick = e => {
      const d = e.target.closest("[data-del]");
      if (d) { e.stopPropagation(); this.deleteStory(d.dataset.del); return; }
      this.openStory(el.dataset.id);
    });
  },

  async deleteStory(id) {
    const s = this.stories.find(x => x.id === id);
    if (!await this.confirm(`Xoá truyện “${s ? s.title : ""}”? Không thể khôi phục.`, "Xoá", true)) return;
    await api("/api/stories/" + id, { method: "DELETE" });
    if (this.story && this.story.id === id) this.story = null;
    this.loadLibrary();
  },

  async loadDraftFile(f) {
    if (!f) return;
    const buf = await f.arrayBuffer();
    let bin = ""; const bytes = new Uint8Array(buf);
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    const r = await api("/api/extract_text", { body: { name: f.name, b64: btoa(bin) } });
    if (r.text) { $("#ideaText").value = r.text; toast(`Đã nạp ${words(r.text).toLocaleString("vi")} từ từ ${f.name}`); }
    else toast("Không đọc được file", true);
  },

  async plan() {
    const text = $("#ideaText").value.trim();
    if (!text) { toast("Hãy nhập ý tưởng hoặc dán bản nháp trước nhé."); $("#ideaText").focus(); return; }
    const isDraft = this.ideaMode === "draft";
    const opts = {
      idea: isDraft ? "" : text, draft: isDraft ? text : "",
      chapters: Math.max(1, Math.min(200, +$("#optChapters").value || 12)),
      genre: $("#optGenre").value, language: $("#optLang").value, rating: $("#optRating").value
    };
    $("#planLive").classList.remove("hidden");
    const pre = $("#planStream"); pre.textContent = "";
    $("#planStatus").textContent = "AI đang dựng tên truyện, nhân vật, thế giới và dàn ý…";
    const r = await this.ai("plan", opts, { onTok: t => { pre.textContent += t; pre.scrollTop = pre.scrollHeight; } });
    $("#planLive").classList.add("hidden");
    if (!r.json) {
      if (!r.error && !r.stopped) toast("AI không trả về dàn ý, thử lại nhé.", true);
      return;
    }
    const j = r.json;
    const chapters = (j.chapters || []).map(c => ({
      id: uid(), title: String(c.title || "").trim() || "Chương mới",
      outline: String(c.outline || c.summary || "").trim(), content: "", summary: ""
    }));
    if (isDraft && $("#draftAsCh1").checked) {
      if (!chapters.length) chapters.push({ id: uid(), title: "Chương 1", outline: "", content: "", summary: "" });
      chapters[0].content = text;
    }
    const st = await api("/api/stories", {
      body: {
        title: j.title || "Truyện mới", genre: j.genre || opts.genre, logline: j.logline || "",
        style: j.style || "", pov: j.pov || "", world: j.world || "",
        characters: (j.characters || []).map(c => ({ id: uid(), name: c.name || "", role: c.role || "", age: String(c.age ?? ""), desc: c.desc || c.description || "" })),
        chapters, rating: opts.rating, language: opts.language, idea: text.slice(0, 4000)
      }
    });
    $("#ideaText").value = "";
    toast(`Đã dựng xong “${st.title}” với ${chapters.length} chương!`);
    await this.loadLibrary();
    this.openStory(st.id, "outline");
  },

  async blankStory() {
    const st = await api("/api/stories", { body: { title: "Truyện mới", rating: $("#optRating").value,
      chapters: [{ id: uid(), title: "Chương 1", outline: "", content: "", summary: "" }] } });
    await this.loadLibrary();
    this.openStory(st.id, "overview");
  },

  openFolder(path) { api("/api/open", { body: { path: path || this.info.data_dir } }); },

  goLibrary() {
    this.saveNow();
    this.story = null;
    $("#storyView").classList.add("hidden");
    $("#libraryView").classList.remove("hidden");
    $("#crumbs").innerHTML = "";
    this.hideSel(); this.hideEdit();
    this.loadLibrary();
  },

  /* ================== truyện ================== */
  async openStory(id, pane) {
    const st = await api("/api/stories/" + id);
    if (st.error) { toast(st.error, true); return; }
    st.chapters = st.chapters || []; st.characters = st.characters || []; st.chat = st.chat || [];
    st.chapters.forEach(c => c.id = c.id || uid());
    this.story = st;
    $("#libraryView").classList.add("hidden");
    $("#storyView").classList.remove("hidden");
    this.renderSide();
    this.renderChat();
    const firstEmpty = st.chapters.findIndex(c => !(c.content || "").trim());
    this.show(pane || (st.chapters.some(c => (c.content || "").trim()) ? "ch:" + Math.max(0, firstEmpty < 0 ? st.chapters.length - 1 : firstEmpty) : "outline"));
  },

  renderSide() {
    const st = this.story;
    $("#sideTitle").textContent = st.title;
    $("#crumbs").innerHTML = `Thư viện › <b>${esc(st.title)}</b> <span class="tag r-${st.rating}">${RATING_LABEL[st.rating] || ""}</span>`;
    $("#chList").innerHTML = st.chapters.map((c, i) => {
      const w = words(c.content);
      return `<button class="ch-item" data-i="${i}"><span class="n">${i + 1}</span><span class="t">${esc(c.title || "Chưa đặt tên")}</span>
        <span class="st" title="${w ? w + " từ" : "chưa viết"}">${w ? "✓" : "○"}</span></button>`;
    }).join("");
    $$(".ch-item").forEach(b => b.onclick = () => this.show("ch:" + b.dataset.i));
    this.markNav();
  },

  markNav() {
    $$(".side-nav button").forEach(b => b.classList.toggle("on", b.dataset.pane === this.pane));
    $$(".ch-item").forEach(b => b.classList.toggle("on", "ch:" + b.dataset.i === this.pane));
  },

  show(pane) {
    if (this.cur && this.pane !== pane && this.pane.startsWith("ch:")) { toast("Đang viết – bấm ⏹ Dừng trước khi chuyển trang."); return; }
    this.hideSel(); this.hideEdit();
    this.pane = pane;
    this.markNav();
    const c = $("#center"); c.scrollTop = 0;
    if (pane === "overview") this.renderOverview();
    else if (pane === "characters") this.renderCharacters();
    else if (pane === "world") this.renderWorld();
    else if (pane === "outline") this.renderOutline();
    else if (pane.startsWith("ch:")) this.renderChapter(+pane.slice(3));
  },

  /* ---------- lưu ---------- */
  scheduleSave() {
    if (!this.story) return;
    $("#saveState").textContent = "Đang lưu…";
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => this.saveNow(), 900);
  },
  saveNow(beacon) {
    if (!this.story) return;
    clearTimeout(this.saveTimer);
    const body = JSON.stringify(this.story);
    if (beacon) { fetch("/api/stories/" + this.story.id, { method: "PUT", body, keepalive: true, headers: { "Content-Type": "application/json" } }); return; }
    return fetch("/api/stories/" + this.story.id, { method: "PUT", body, headers: { "Content-Type": "application/json" } })
      .then(() => { $("#saveState").textContent = "Đã lưu " + new Date().toLocaleTimeString("vi"); })
      .catch(() => { $("#saveState").textContent = "⚠ Lưu thất bại"; });
  },
  bindField(el, obj, key, after) {
    el.value = obj[key] ?? "";
    el.addEventListener("input", () => { obj[key] = el.value; this.scheduleSave(); after && after(); });
  },

  /* ---------- Tổng quan ---------- */
  renderOverview() {
    const st = this.story;
    $("#center").innerHTML = `<div class="pane">
      <h2>Tổng quan</h2><p class="hint">Thông tin chung AI dùng mỗi lần viết. Sửa thoải mái.</p>
      <div class="form">
        <label class="full">Tên truyện<input id="f_title" class="big-title"></label>
        <label>Thể loại<input id="f_genre"></label>
        <label>Ngôi kể<input id="f_pov" placeholder="VD: ngôi thứ ba, bám nữ chính"></label>
        <label class="full">Giới thiệu / logline<textarea id="f_logline"></textarea></label>
        <label class="full">Giọng văn<textarea id="f_style" placeholder="VD: lạnh, gọn, nhiều ẩn dụ; thoại sắc sảo"></textarea></label>
        <label>Ngôn ngữ<select id="f_language"><option>Tiếng Việt</option><option>English</option></select></label>
        <label>Giới hạn nội dung (riêng truyện này)
          <select id="f_rating"><option value="all">Mọi lứa tuổi</option><option value="18">18+</option><option value="nsfw">NSFW (18+ có cảnh nóng)</option></select>
        </label>
        <label class="full">Ghi chú cho AI (luật lệ, điều cần nhớ, phong cách riêng…)<textarea id="f_notes"></textarea></label>
        <label class="full">Ý tưởng gốc<textarea id="f_idea"></textarea></label>
      </div>
      <h2 style="margin-top:28px;font-size:20px">Xuất truyện</h2>
      <p class="hint">Chỉ xuất các chương đã viết.</p>
      <div class="export-row">
        <button class="primary" onclick="App.exportAs('docx')">📄 Word (.docx)</button>
        <button class="primary" onclick="App.exportAs('epub')">📚 EPUB</button>
        <button class="primary" onclick="App.exportAs('txt')">📝 TXT</button>
        <button class="ghost-btn" onclick="App.openFolder(App.info.data_dir + '/exports')">📁 Thư mục xuất</button>
      </div>
      <div style="margin-top:36px"><button class="danger-btn" onclick="App.deleteStory(App.story.id)">🗑 Xoá truyện này</button></div>
    </div>`;
    for (const k of ["title", "genre", "pov", "logline", "style", "language", "rating", "notes", "idea"])
      this.bindField($("#f_" + k), st, k, k === "title" || k === "rating" ? () => this.renderSide() : null);
  },

  async exportAs(fmt) {
    await this.saveNow();
    const r = await api("/api/export", { body: { id: this.story.id, fmt, ask: !!this.info.native_window } });
    if (r.cancelled) return;
    if (r.error) { toast(r.error, true); return; }
    this.lastExport = r.path;
    toast(`Đã xuất: ${esc(r.path)} &nbsp; <a href="#" style="color:inherit;font-weight:700" onclick="App.openFolder(App.lastExport);return false">Mở thư mục</a>`, false, 8000, true);
  },

  /* ---------- Nhân vật ---------- */
  renderCharacters() {
    const st = this.story;
    $("#center").innerHTML = `<div class="pane">
      <h2>Nhân vật</h2><p class="hint">Tên, vai trò, tuổi và mô tả (ngoại hình, tính cách, động cơ, bí mật).</p>
      <div id="charList"></div>
      <button class="ghost-btn" onclick="App.addChar()">＋ Thêm nhân vật</button></div>`;
    const L = $("#charList");
    L.innerHTML = st.characters.map((c, i) => `<div class="card char-card" data-i="${i}">
        <input data-k="name" placeholder="Tên"><input data-k="role" placeholder="Vai trò"><input data-k="age" placeholder="Tuổi">
        <button class="mini" title="Xoá" data-rm="${i}">🗑</button>
        <textarea data-k="desc" placeholder="Mô tả"></textarea></div>`).join("");
    $$(".char-card", L).forEach(card => {
      const c = st.characters[+card.dataset.i];
      $$("[data-k]", card).forEach(el => this.bindField(el, c, el.dataset.k));
    });
    $$("[data-rm]", L).forEach(b => b.onclick = () => { st.characters.splice(+b.dataset.rm, 1); this.scheduleSave(); this.renderCharacters(); });
  },
  addChar() { this.story.characters.push({ id: uid(), name: "", role: "", age: "", desc: "" }); this.scheduleSave(); this.renderCharacters(); $$(".char-card input").slice(-3)[0].focus(); },

  /* ---------- Thế giới ---------- */
  renderWorld() {
    $("#center").innerHTML = `<div class="pane">
      <h2>Thế giới</h2><p class="hint">Bối cảnh, lịch sử, hệ thống sức mạnh, địa danh, luật lệ… AI sẽ bám theo khi viết.</p>
      <textarea id="f_world" style="width:100%;min-height:60vh;font-family:var(--serif);font-size:16px;line-height:1.7"></textarea></div>`;
    this.bindField($("#f_world"), this.story, "world");
  },

  /* ---------- Dàn ý ---------- */
  renderOutline() {
    const st = this.story;
    $("#center").innerHTML = `<div class="pane">
      <h2>Dàn ý từng chương</h2><p class="hint">Sửa dàn ý trước khi viết để AI đi đúng hướng. Bấm ✍ để mở chương.</p>
      <div id="olList"></div>
      <div class="row">
        <button class="ghost-btn" onclick="App.addChapter(true)">＋ Thêm chương</button>
        <span style="flex:1"></span>
        <label class="row" style="gap:6px;color:var(--muted)">AI viết thêm dàn ý <input type="number" id="extN" value="5" min="1" max="50" style="width:64px"> chương</label>
        <button class="primary needs-idle" onclick="App.extendOutline()">✨ Thêm</button>
        <button class="ghost-btn needs-busy hidden" onclick="App.stop()">⏹ Dừng</button>
      </div>
      <pre id="extStream" class="note" style="white-space:pre-wrap;max-height:200px;overflow:auto"></pre></div>`;
    $("#olList").innerHTML = st.chapters.map((c, i) => `<div class="card ol-item" data-i="${i}">
        <div class="num">${i + 1}</div>
        <div><input data-k="title" placeholder="Tên chương"><textarea data-k="outline" placeholder="Dàn ý chương"></textarea>
          <div class="note">${words(c.content) ? "✓ Đã viết " + words(c.content).toLocaleString("vi") + " từ" : "Chưa viết"}</div></div>
        <div class="ol-tools">
          <button class="mini" title="Viết / mở chương" data-open="${i}">✍</button>
          <button class="mini" title="Lên" data-up="${i}">↑</button>
          <button class="mini" title="Xuống" data-down="${i}">↓</button>
          <button class="mini" title="Xoá chương" data-rm="${i}">🗑</button>
        </div></div>`).join("") || `<div class="empty">Chưa có chương nào.</div>`;
    $$(".ol-item").forEach(el => {
      const c = st.chapters[+el.dataset.i];
      $$("[data-k]", el).forEach(f => this.bindField(f, c, f.dataset.k, f.dataset.k === "title" ? () => this.renderSide() : null));
    });
    $$("[data-open]").forEach(b => b.onclick = () => this.show("ch:" + b.dataset.open));
    $$("[data-up]").forEach(b => b.onclick = () => this.moveCh(+b.dataset.up, -1));
    $$("[data-down]").forEach(b => b.onclick = () => this.moveCh(+b.dataset.down, 1));
    $$("[data-rm]").forEach(b => b.onclick = () => this.removeCh(+b.dataset.rm));
    this.setBusy(!!this.cur);
  },
  moveCh(i, d) {
    const a = this.story.chapters, j = i + d;
    if (j < 0 || j >= a.length) return;
    [a[i], a[j]] = [a[j], a[i]];
    this.scheduleSave(); this.renderSide(); this.renderOutline();
  },
  async removeCh(i) {
    const c = this.story.chapters[i];
    if ((c.content || "").trim() && !await this.confirm(`Xoá chương ${i + 1} “${c.title}” cùng ${words(c.content)} từ đã viết?`, "Xoá", true)) return;
    this.story.chapters.splice(i, 1);
    this.scheduleSave(); this.renderSide(); this.renderOutline();
  },
  addChapter(stay) {
    const n = this.story.chapters.length + 1;
    this.story.chapters.push({ id: uid(), title: "Chương " + n, outline: "", content: "", summary: "" });
    this.scheduleSave(); this.renderSide();
    if (stay === true) this.renderOutline(); else this.show("ch:" + (n - 1));
  },
  async extendOutline() {
    const n = Math.max(1, Math.min(50, +$("#extN").value || 5));
    const pre = $("#extStream"); pre.textContent = "";
    const r = await this.ai("extend_outline", { story: this.story, count: n }, { onTok: t => { pre.textContent += t; pre.scrollTop = pre.scrollHeight; } });
    if (r.json && Array.isArray(r.json.chapters)) {
      r.json.chapters.forEach(c => this.story.chapters.push({ id: uid(), title: c.title || "Chương mới", outline: c.outline || "", content: "", summary: "" }));
      this.scheduleSave(); this.renderSide(); this.renderOutline();
      toast(`Đã thêm ${r.json.chapters.length} chương vào dàn ý.`);
    }
  },

  /* ---------- Trình soạn chương ---------- */
  renderChapter(i) {
    const st = this.story, c = st.chapters[i];
    if (!c) { this.show("outline"); return; }
    $("#center").innerHTML = `<div class="ed-wrap">
      <div class="ed-head">
        <div class="ttl"><span class="no">Chương ${i + 1}</span><input id="chTitle" placeholder="Tên chương"></div>
        <details class="ed-outline" ${(c.content || "").trim() ? "" : "open"}><summary>Dàn ý chương</summary><textarea id="chOutline" placeholder="AI sẽ viết theo dàn ý này"></textarea></details>
        <details class="ed-outline"><summary>Tóm tắt (AI tự tạo để nhớ mạch truyện)</summary>
          <textarea id="sumText" placeholder="Sẽ tự tạo khi bạn viết các chương sau"></textarea>
          <button class="ghost-btn sm needs-idle" onclick="App.resummarize(${i})" style="margin-top:6px">↻ Tóm tắt lại</button></details>
        <div class="toolbar">
          <button class="tool main needs-idle" onclick="App.writeChapter(${i})" title="Viết cả chương theo dàn ý">✍ Viết chương</button>
          <button class="tool needs-idle" onclick="App.continueWriting(${i})" title="Viết tiếp từ vị trí con trỏ (Ctrl+Enter)">➜ Viết tiếp</button>
          <button class="tool stop needs-busy hidden" onclick="App.stop()">⏹ Dừng</button>
          <button class="tool needs-idle" onclick="App.undoCh(${i})" title="Hoàn tác thao tác AI gần nhất">↶ Hoàn tác</button>
          <input id="aiExtra" placeholder="Ghi chú cho AI (tuỳ chọn): VD thêm nhiều thoại…" style="flex:1;min-width:180px">
          <span class="wc" id="wc"></span>
          <button class="tool" title="Chương trước" onclick="App.show('ch:${i - 1}')" ${i ? "" : "disabled"}>‹</button>
          <button class="tool" title="Chương sau" onclick="App.show('ch:${i + 1}')" ${i + 1 < st.chapters.length ? "" : "disabled"}>›</button>
        </div>
        <div class="status-line" id="stLine"></div>
      </div>
      <div class="ed-scroll" id="edScroll"><div class="paper"><textarea id="editor" spellcheck="false" placeholder="Bắt đầu viết, hoặc bấm ✍ Viết chương để AI viết theo dàn ý. Bôi đen một đoạn để AI viết lại, mở rộng, rút gọn hay đổi giọng văn."></textarea></div></div>
    </div>`;
    this.bindField($("#chTitle"), c, "title", () => this.renderSide());
    this.bindField($("#chOutline"), c, "outline");
    this.bindField($("#sumText"), c, "summary");
    const ed = $("#editor");
    ed.value = c.content || "";
    ed.addEventListener("input", () => { c.content = ed.value; this.edChanged(i); this.scheduleSave(); });
    ed.addEventListener("mouseup", e => setTimeout(() => this.maybeSel(e), 0));
    ed.addEventListener("keyup", e => { if (e.shiftKey || e.key === "a") this.maybeSel(null); });
    ed.addEventListener("keydown", e => { if (e.key === "Enter" && e.ctrlKey) { e.preventDefault(); this.continueWriting(i); } });
    ed.addEventListener("scroll", () => this.hideSel());
    $("#edScroll").addEventListener("scroll", () => this.hideSel());
    this.edChanged(i, true);
    this.setBusy(!!this.cur);
  },

  edChanged(i, first) {
    const ed = $("#editor"); if (!ed) return;
    ed.style.height = "auto"; ed.style.height = Math.max(ed.scrollHeight, 300) + "px";
    $("#wc").textContent = words(ed.value).toLocaleString("vi") + " từ";
    if (!first) {
      const item = $(`.ch-item[data-i="${i}"] .st`);
      if (item) item.textContent = ed.value.trim() ? "✓" : "○";
    }
  },

  pushUndo(i) {
    const c = this.story.chapters[i];
    const k = c.id; (this.undo[k] = this.undo[k] || []).push(c.content || "");
    if (this.undo[k].length > 30) this.undo[k].shift();
  },
  undoCh(i) {
    const c = this.story.chapters[i], s = this.undo[c.id];
    if (!s || !s.length) { toast("Không còn gì để hoàn tác."); return; }
    c.content = s.pop();
    const ed = $("#editor"); if (ed) { ed.value = c.content; this.edChanged(i); }
    this.scheduleSave();
  },

  /** Stream chữ vào editor tại vị trí pos. */
  streamInto(i, pos) {
    const c = this.story.chapters[i];
    const sc = $("#edScroll");
    return t => {
      const ed = $("#editor");
      const v = c.content || "";
      c.content = v.slice(0, pos) + t + v.slice(pos);
      pos += t.length;
      if (ed && this.pane === "ch:" + i) {
        const atEnd = pos >= c.content.length - 1;
        ed.value = c.content; this.edChanged(i);
        if (atEnd && sc) sc.scrollTop = sc.scrollHeight;
      }
    };
  },

  async writeChapter(i) {
    const c = this.story.chapters[i];
    if (!(c.outline || "").trim() && !await this.confirm("Chương này chưa có dàn ý. AI sẽ tự nghĩ nội dung dựa trên mạch truyện. Tiếp tục?", "Viết luôn")) return;
    if ((c.content || "").trim()) {
      if (!await this.confirm("Chương đã có nội dung. Viết lại từ đầu? (Nội dung cũ vẫn khôi phục được bằng ↶ Hoàn tác)", "Viết lại từ đầu")) return;
    }
    this.pushUndo(i);
    c.content = "";
    $("#editor").value = "";
    this.edChanged(i);
    $("#stLine").innerHTML = `<span class="spinner"></span> <span id="stTxt">AI đang viết chương ${i + 1}…</span>`;
    const r = await this.ai("write_chapter", { story: this.story, index: i, extra: $("#aiExtra").value },
      { onTok: this.streamInto(i, 0), onStatus: s => { const e = $("#stTxt"); if (e) e.textContent = s; } });
    this.afterWrite(i, r);
  },

  async continueWriting(i) {
    const c = this.story.chapters[i], ed = $("#editor");
    const content = c.content || "";
    let pos = ed && document.activeElement === ed ? ed.selectionEnd : content.length;
    if (pos === 0 && content.length) pos = content.length;
    let before = content.slice(0, pos), after = content.slice(pos);
    this.pushUndo(i);
    // thêm khoảng ngắt cho tự nhiên
    let lead = "";
    if (before.trim()) lead = /\n\s*$/.test(before) ? "" : (/[.!?…"”]\s*$/.test(before) ? "\n\n" : " ");
    if (lead) { c.content = before + lead + after; pos += lead.length; before += lead; }
    $("#stLine").innerHTML = `<span class="spinner"></span> <span id="stTxt">AI đang viết tiếp…</span>`;
    const r = await this.ai("continue", { story: this.story, index: i, before, after, extra: $("#aiExtra").value },
      { onTok: this.streamInto(i, pos), onStatus: s => { const e = $("#stTxt"); if (e) e.textContent = s; } });
    this.afterWrite(i, r);
  },

  afterWrite(i, r) {
    const line = $("#stLine");
    if (line) line.innerHTML = r.error ? `<span style="color:var(--danger)">⚠ ${esc(r.error)}</span>` : (r.stopped ? "Đã dừng." : "");
    if (line && !r.error) setTimeout(() => { if (line.textContent === "Đã dừng.") line.textContent = ""; }, 3000);
    this.scheduleSave(); this.renderSide(); this.markNav();
  },

  async resummarize(i) {
    const c = this.story.chapters[i];
    if (!(c.content || "").trim()) { toast("Chương chưa có nội dung để tóm tắt."); return; }
    c.summary_hash = ""; c.summary = "";
    $("#sumText").value = "Đang tóm tắt…";
    await this.ai("summaries", { story: this.story, upto: i + 1 });
  },

  /* ---------- Bôi đen ---------- */
  maybeSel(e) {
    const ed = $("#editor");
    if (!ed || this.cur) return;
    const a = ed.selectionStart, b = ed.selectionEnd;
    if (b - a < 3) { this.hideSel(); return; }
    const m = $("#selMenu");
    m.classList.remove("hidden"); $("#toneList").classList.add("hidden");
    const r = ed.getBoundingClientRect();
    let x = e ? e.clientX : r.left + 80, y = e ? e.clientY : Math.max(r.top + 20, 160);
    const w = m.offsetWidth;
    x = Math.max(10, Math.min(window.innerWidth - w - 10, x - w / 2));
    y = y - 52 < 60 ? y + 18 : y - 52;
    m.style.left = x + "px"; m.style.top = y + "px";
    this.selPos = { x, y };
  },
  hideSel() { $("#selMenu").classList.add("hidden"); $("#toneList").classList.add("hidden"); },

  async selAction(act) {
    if (act === "tone-menu") { $("#toneList").classList.toggle("hidden"); return; }
    if (act === "custom") {
      const ins = await this.prompt("Bạn muốn AI sửa đoạn này thế nào?", "VD: thêm đối thoại giữa hai nhân vật, làm cảnh căng thẳng hơn…");
      if (ins) this.startEdit("custom", { instruction: ins });
      return;
    }
    this.startEdit(act, {});
  },

  async startEdit(mode, opt, retry) {
    const i = +this.pane.slice(3), ed = $("#editor"), c = this.story.chapters[i];
    if (!retry) {
      const a = ed.selectionStart, b = ed.selectionEnd;
      if (b - a < 1) return;
      this.editReq = { i, a, b, mode, opt, text: c.content.slice(a, b) };
    }
    this.hideSel();
    const R = this.editReq, content = c.content || "";
    const titles = { rewrite: "↻ Viết lại", expand: "⤢ Mở rộng", shorten: "⤡ Rút gọn", tone: "🎭 Giọng: " + (opt.tone || ""), custom: "✎ " + (opt.instruction || "") };
    const pop = $("#editPop");
    $("#editTitle").textContent = titles[mode] || "Sửa";
    $("#editBody").textContent = "";
    $("#editSpin").classList.remove("hidden");
    $$("#editPop .edit-actions button").forEach(b => b.disabled = b.id !== "editCancel");
    pop.classList.remove("hidden");
    const p = this.selPos || { x: 200, y: 200 };
    pop.style.left = Math.max(10, Math.min(window.innerWidth - pop.offsetWidth - 10, p.x)) + "px";
    pop.style.top = Math.max(60, Math.min(window.innerHeight - pop.offsetHeight - 20, p.y + 50)) + "px";
    const body = $("#editBody");
    const r = await this.ai("edit", {
      story: this.story, index: i, selected: R.text, before: content.slice(0, R.a), after: content.slice(R.b),
      mode, tone: opt.tone || "", instruction: opt.instruction || ""
    }, { onTok: (t, all) => { body.textContent = all; body.scrollTop = body.scrollHeight; pop.style.top = Math.max(60, Math.min(window.innerHeight - pop.offsetHeight - 20, parseFloat(pop.style.top))) + "px"; } });
    $("#editSpin").classList.add("hidden");
    this.editResult = r.text.trim();
    $$("#editPop .edit-actions button").forEach(b => b.disabled = false);
    if (!this.editResult) $("#editReplace").disabled = $("#editInsert").disabled = true;
  },

  applyEdit(how) {
    const R = this.editReq, c = this.story.chapters[R.i];
    if (!this.editResult) return;
    if (c.content.slice(R.a, R.b) !== R.text) { toast("Đoạn văn đã thay đổi, không thể áp dụng. Hãy bôi đen lại.", true); this.hideEdit(); return; }
    this.pushUndo(R.i);
    const ins = how === "replace" ? this.editResult : R.text + "\n\n" + this.editResult;
    c.content = c.content.slice(0, R.a) + ins + c.content.slice(R.b);
    const ed = $("#editor");
    if (ed) { ed.value = c.content; this.edChanged(R.i); ed.focus(); ed.setSelectionRange(R.a, R.a + ins.length); }
    this.scheduleSave(); this.hideEdit();
  },
  hideEdit() { $("#editPop").classList.add("hidden"); },

  /* ================== chat ================== */
  renderChat() {
    const log = $("#chatLog"), msgs = this.story.chat;
    if (!msgs.length) {
      log.innerHTML = `<div class="chat-welcome">Hỏi mình bất cứ điều gì về truyện: gợi ý tình tiết, đặt tên, phân tích nhân vật, soát lỗi logic… Mình đã đọc tổng quan, nhân vật, dàn ý và tóm tắt các chương.</div>`;
      return;
    }
    log.innerHTML = msgs.map((m, k) => `<div class="msg ${m.role}">${esc(m.content)}${m.role === "assistant" ? `<button class="copy" data-k="${k}">Sao chép</button>` : ""}</div>`).join("");
    $$(".copy", log).forEach(b => b.onclick = () => { navigator.clipboard.writeText(msgs[+b.dataset.k].content); toast("Đã sao chép"); });
    log.scrollTop = log.scrollHeight;
  },
  quickChat(t) { $("#chatText").value = t; this.sendChat(); },
  async sendChat() {
    const ta = $("#chatText"), t = ta.value.trim();
    if (!t || !this.story) return;
    if (this.cur) { toast("AI đang bận."); return; }
    ta.value = "";
    const msgs = this.story.chat;
    msgs.push({ role: "user", content: t });
    this.renderChat();
    const log = $("#chatLog");
    const div = document.createElement("div"); div.className = "msg assistant"; div.innerHTML = '<span class="spinner"></span>';
    log.appendChild(div); log.scrollTop = log.scrollHeight;
    const r = await this.ai("chat", { story: this.story, messages: msgs }, { onTok: (x, all) => { div.textContent = all; log.scrollTop = log.scrollHeight; } });
    if (r.text.trim()) msgs.push({ role: "assistant", content: r.text.trim() });
    else if (r.error) msgs.push({ role: "assistant", content: "⚠ " + r.error });
    this.scheduleSave(); this.renderChat();
  },
  async clearChat() {
    if (!this.story.chat.length || !await this.confirm("Xoá toàn bộ hội thoại với trợ lý?", "Xoá")) return;
    this.story.chat = []; this.scheduleSave(); this.renderChat();
  },
  toggleChat() {
    this.chatOpen = !this.chatOpen;
    $("#chatPanel").classList.toggle("hidden", !this.chatOpen);
    $("#chatTab").classList.toggle("hidden", this.chatOpen);
  },

  /* ================== modal ================== */
  modal(html) { $("#modal").innerHTML = html; $("#modalBg").classList.remove("hidden"); },
  closeModal() { $("#modalBg").classList.add("hidden"); if (this._mres) { this._mres(null); this._mres = null; } },
  confirm(text, ok = "Đồng ý", danger = false) {
    return new Promise(res => {
      this._mres = res;
      this.modal(`<p style="font-size:15px;line-height:1.5">${esc(text)}</p><div class="modal-actions">
        <button class="ghost-btn" id="mNo">Huỷ</button><button class="${danger ? "danger-btn" : "primary"}" id="mYes">${esc(ok)}</button></div>`);
      $("#mNo").onclick = () => { this._mres = null; $("#modalBg").classList.add("hidden"); res(false); };
      $("#mYes").onclick = () => { this._mres = null; $("#modalBg").classList.add("hidden"); res(true); };
      $("#mYes").focus();
    });
  },
  prompt(text, ph = "") {
    return new Promise(res => {
      this._mres = res;
      this.modal(`<h3>${esc(text)}</h3><textarea id="mIn" style="width:100%;min-height:90px" placeholder="${esc(ph)}"></textarea>
        <div class="modal-actions"><button class="ghost-btn" id="mNo">Huỷ</button><button class="primary" id="mYes">OK</button></div>`);
      const done = v => { this._mres = null; $("#modalBg").classList.add("hidden"); res(v); };
      $("#mNo").onclick = () => done(null);
      $("#mYes").onclick = () => done($("#mIn").value.trim());
      $("#mIn").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); done($("#mIn").value.trim()); } });
      $("#mIn").focus();
    });
  },

  /* ================== cài đặt ================== */
  async openSettings() {
    const s = this.settings;
    const pOpts = Object.entries(this.presets).map(([k, v]) => `<option value="${k}">${esc(v.label)}</option>`).join("");
    this.modal(`<h3>⚙ Cài đặt</h3>
      <div class="form">
        <label>Phần mềm chạy model<select id="s_provider">${pOpts}</select></label>
        <label>Địa chỉ API<input id="s_base_url"></label>
        <label class="full">Model
          <div class="row"><select id="s_model" style="flex:1"></select><button class="ghost-btn" id="s_fetch">↻ Tải danh sách</button></div>
          <span class="note" id="s_mstatus"></span></label>
        <label>API key (để trống nếu chạy local)<input id="s_api_key" type="password"></label>
        <label>Nhiệt độ sáng tạo (0.1–1.5)<input id="s_temperature" type="number" step="0.05" min="0" max="2"></label>
        <label>Số token tối đa mỗi lần viết<input id="s_max_tokens" type="number" step="256" min="256"></label>
        <label>Độ dài chương mong muốn (từ)<input id="s_chapter_words" type="number" step="100" min="300"></label>
        <label>Ngữ cảnh gửi cho AI (ký tự)<input id="s_context_chars" type="number" step="1000" min="4000"></label>
        <label>Cỡ chữ trình soạn<input id="s_font_size" type="number" min="12" max="30"></label>
        <label class="full chk" style="flex-direction:row"><input type="checkbox" id="s_no_think"> Tắt chế độ “suy nghĩ” (Qwen3 /no_think) để viết nhanh hơn</label>
        <label class="full chk" style="flex-direction:row"><input type="checkbox" id="s_check_update_on_start"> Tự kiểm tra bản cập nhật khi mở app</label>
      </div>
      <p class="note" style="margin-top:14px">Gợi ý cho RTX 3060 12GB + RAM 32GB: model 12–14B bản Q4_K_M/Q5_K_M chạy hoàn toàn trên GPU rất nhanh; model 24–27B bản Q4 sẽ tràn sang RAM nên chậm hơn (khoảng vài token/giây) nhưng viết hay hơn. Đặt context của model ≥ 16k trong LM Studio/KoboldCpp và để “Ngữ cảnh gửi cho AI” khoảng 3 ký tự × số token context × 0,6.<br>
      Dữ liệu lưu tại: <code>${esc(this.info.data_dir)}</code></p>
      <div class="modal-actions">
        <span class="note" style="margin-right:auto">Phiên bản ${esc(this.info.version)}</span>
        <button class="ghost-btn" onclick="App.closeModal()">Đóng</button>
        <button class="primary" id="s_save">Lưu</button>
      </div>`);
    const nums = ["temperature", "max_tokens", "chapter_words", "context_chars", "font_size"];
    for (const k of ["provider", "base_url", "api_key", ...nums]) $("#s_" + k).value = s[k] ?? "";
    $("#s_no_think").checked = !!s.no_think;
    $("#s_check_update_on_start").checked = !!s.check_update_on_start;
    $("#s_provider").onchange = e => { const p = this.presets[e.target.value]; if (p && p.base_url) $("#s_base_url").value = p.base_url; };
    const fill = (list, cur) => {
      const all = Array.from(new Set([...(cur ? [cur] : []), ...list]));
      $("#s_model").innerHTML = all.length ? all.map(m => `<option>${esc(m)}</option>`).join("") : `<option value="">(chưa có model)</option>`;
      if (cur) $("#s_model").value = cur;
    };
    fill([], s.model);
    const fetchModels = async () => {
      $("#s_mstatus").textContent = "Đang kết nối…";
      await api("/api/settings", { body: { base_url: $("#s_base_url").value, api_key: $("#s_api_key").value } });
      const r = await api("/api/models");
      if (r.error) { $("#s_mstatus").innerHTML = `<span style="color:var(--danger)">${esc(r.error)}</span>`; return; }
      fill(r.models, s.model && r.models.includes(s.model) ? s.model : r.models[0]);
      $("#s_mstatus").innerHTML = `<span style="color:var(--ok)">✔ Kết nối được – ${r.models.length} model</span>`;
    };
    $("#s_fetch").onclick = fetchModels;
    fetchModels();
    $("#s_save").onclick = async () => {
      const ns = {
        provider: $("#s_provider").value, base_url: $("#s_base_url").value.trim(), api_key: $("#s_api_key").value.trim(),
        model: $("#s_model").value, no_think: $("#s_no_think").checked, check_update_on_start: $("#s_check_update_on_start").checked
      };
      nums.forEach(k => ns[k] = +$("#s_" + k).value);
      const r = await api("/api/settings", { body: ns });
      this.settings = r.settings; this.applyUi(); this.closeModal(); this.refreshModel();
      if (this.pane.startsWith("ch:") && this.story) this.edChanged(+this.pane.slice(3), true);
      toast("Đã lưu cài đặt");
    };
  },

  toggleTheme() {
    const t = (this.settings.ui_theme || "dark") === "dark" ? "light" : "dark";
    this.settings.ui_theme = t; this.applyUi();
    api("/api/settings", { body: { ui_theme: t } });
  },

  /* ================== cập nhật ================== */
  async checkUpdateQuiet() {
    const r = await api("/api/update/check").catch(() => null);
    if (r && r.has_update) { $("#updBadge").classList.remove("hidden"); this.updInfo = r; toast(`Có bản mới ${r.latest}! Bấm ⟳ để cập nhật.`); }
  },
  async openUpdate() {
    this.modal(`<h3>⟳ Cập nhật</h3><p><span class="spinner"></span> Đang kiểm tra GitHub…</p>`);
    const r = await api("/api/update/check");
    if (r.error) {
      this.modal(`<h3>⟳ Cập nhật</h3><p>${esc(r.error)}</p><p class="note">Bản hiện tại: ${esc(r.current)}</p>
        <div class="modal-actions"><button class="ghost-btn" onclick="App.openUrl('${esc(r.page)}')">Mở trang Releases</button><button class="primary" onclick="App.closeModal()">Đóng</button></div>`);
      return;
    }
    if (!r.has_update) {
      $("#updBadge").classList.add("hidden");
      this.modal(`<h3>⟳ Cập nhật</h3><p>✔ Bạn đang dùng bản mới nhất (${esc(r.current)}).</p>
        <div class="modal-actions"><button class="primary" onclick="App.closeModal()">Đóng</button></div>`);
      return;
    }
    const mb = r.size ? (r.size / 1048576).toFixed(1) + " MB" : "";
    this.modal(`<h3>⟳ Có bản mới ${esc(r.latest)}</h3>
      <p class="note">Bản hiện tại: ${esc(r.current)}. Truyện và cài đặt trong thư mục <code>data</code> được giữ nguyên.</p>
      ${r.notes ? `<div class="rel-notes">${esc(r.notes)}</div>` : ""}
      <div class="progress hidden" id="uProg"><div></div></div><p class="note" id="uTxt"></p>
      <div class="modal-actions">
        <button class="ghost-btn" onclick="App.openUrl('${esc(r.page)}')">Xem trên GitHub</button>
        <button class="ghost-btn" onclick="App.closeModal()">Để sau</button>
        ${r.can_self_update && r.url ? `<button class="primary" id="uGo">Tải & cài đặt ${mb ? "(" + mb + ")" : ""}</button>` : ""}
      </div>
      ${r.can_self_update ? "" : `<p class="note">Bản đang chạy từ mã nguồn: hãy tải bản mới trên GitHub hoặc chạy <code>git pull</code>.</p>`}`);
    const go = $("#uGo");
    if (go) go.onclick = () => this.doUpdate(r.url);
  },
  async doUpdate(url) {
    $("#uGo").disabled = true; $("#uProg").classList.remove("hidden");
    const bar = $("#uProg div"), txt = $("#uTxt");
    const resp = await fetch("/api/update/download", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) });
    const reader = resp.body.getReader(), dec = new TextDecoder(); let buf = "", ok = false;
    for (;;) {
      const { value, done } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true }); let k;
      while ((k = buf.indexOf("\n")) >= 0) {
        const ev = JSON.parse(buf.slice(0, k)); buf = buf.slice(k + 1);
        if (ev.t === "progress") { const p = ev.total ? ev.done / ev.total * 100 : 50; bar.style.width = p + "%"; txt.textContent = `Đang tải… ${(ev.done / 1048576).toFixed(1)} MB`; }
        else if (ev.t === "done") ok = true;
        else if (ev.t === "error") { txt.textContent = ev.d; $("#uGo").disabled = false; }
      }
    }
    if (!ok) return;
    bar.style.width = "100%";
    txt.textContent = "Đã tải xong. App sẽ tự đóng, cài bản mới rồi mở lại…";
    await this.saveNow();
    await api("/api/update/apply", { body: {} });
  },
  openUrl(u) { api("/api/open_url", { body: { url: u } }); },
};

App.init();
