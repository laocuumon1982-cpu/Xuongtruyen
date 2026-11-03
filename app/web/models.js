/* Xưởng Truyện – Trung tâm Model AI (tải & chạy model ngay trong app) */
"use strict";

const fmtGB = b => (b / 1073741824).toFixed(b > 10737418240 ? 1 : 2) + " GB";
const fmtSpeed = b => b > 1048576 ? (b / 1048576).toFixed(1) + " MB/s" : (b / 1024).toFixed(0) + " KB/s";

Object.assign(App, {
  mc: null, mcTimer: null, pillTimer: null, engStatus: null,

  /* ---------- trạng thái model trên thanh trên ---------- */
  async refreshModel() {
    const dot = $("#modelDot"), name = $("#modelName");
    if ((this.settings.provider || "builtin") !== "builtin") {
      name.textContent = "Đang kiểm tra model…"; dot.className = "dot";
      const r = await api("/api/models").catch(() => ({ error: "lỗi" }));
      if (r.error || !r.models) { dot.className = "dot bad"; name.textContent = "Chưa kết nối model – bấm để cài đặt"; return false; }
      dot.className = "dot ok"; name.textContent = this.settings.model || r.models[0] || "model";
      return true;
    }
    const st = await api("/api/engine/status").catch(() => null);
    if (!st) return false;
    this.engStatus = st;
    const s = st.server, busy = st.tasks.find(t => t.state === "running");
    if (s.state === "ready") { dot.className = "dot ok"; name.textContent = s.name; }
    else if (s.state === "loading") { dot.className = "dot load"; name.textContent = "Đang nạp " + s.name + "…"; }
    else if (busy) { dot.className = "dot load"; name.textContent = busy.kind === "engine" ? "Đang cài bộ máy…" : `Đang tải ${busy.label} ${busy.total ? Math.floor(busy.done / busy.total * 100) + "%" : ""}`; }
    else if (s.state === "error") { dot.className = "dot bad"; name.textContent = "Model lỗi – bấm để xem"; }
    else { dot.className = "dot bad"; name.textContent = "Chưa chạy model – bấm để chọn"; }
    clearTimeout(this.pillTimer);
    this.pillTimer = setTimeout(() => this.refreshModel(), (s.state === "loading" || busy) ? 1500 : 6000);
    return s.state === "ready";
  },

  /* ---------- màn chào lần đầu ---------- */
  async maybeWelcome() {
    if (this.settings.welcomed || (this.settings.provider || "builtin") !== "builtin") return;
    const st = await api("/api/engine/status?gpu=1");
    const cat = await api("/api/engine/catalog");
    if (st.server.state === "ready" || st.server.state === "loading" || cat.local.length) { this.markWelcomed(); return; }
    const g = st.gpu, rec = cat.catalog.find(c => c.featured) || cat.catalog[0];
    const vram = g ? Math.round(g.total_mb / 1024) : 0;
    this.modal(`<h3>👋 Chào mừng đến Xưởng Truyện!</h3>
      <p style="line-height:1.6">Để AI viết truyện <b>ngay trên máy bạn</b> (riêng tư, không giới hạn, không kiểm duyệt), app cần tải:
      <br>① <b>Bộ máy chạy model</b> llama.cpp ${g ? "bản CUDA cho card NVIDIA" : ""} (khoảng 200–600 MB)
      <br>② <b>Một model AI</b>. Đề xuất cho máy bạn: <b>${esc(rec.name)}</b> (${rec.size_gb} GB) – ${esc(rec.desc)}</p>
      ${g ? `<p class="note">Đã nhận diện: <b>${esc(g.name)}</b> · ${vram} GB VRAM</p>` : `<p class="note">Không thấy card NVIDIA – app sẽ dùng bản Vulkan/CPU (chậm hơn).</p>`}
      <p class="note">Mọi thứ lưu trong thư mục <code>data</code> cạnh app. Tải xong lần sau mở app là dùng ngay.</p>
      <div class="modal-actions">
        <button class="ghost-btn" id="wExt">Tôi dùng LM Studio / Ollama</button>
        <button class="ghost-btn" id="wPick">Chọn model khác</button>
        <button class="primary" id="wGo">⚡ Cài tự động (${rec.size_gb} GB)</button>
      </div>`);
    $("#wGo").onclick = async () => { this.markWelcomed(); await api("/api/engine/quick", { body: { id: rec.id } }); this.openModels(); };
    $("#wPick").onclick = () => { this.markWelcomed(); this.openModels(); };
    $("#wExt").onclick = () => { this.markWelcomed(); this.closeModal(); this.openSettings(); };
  },
  markWelcomed() { this.settings.welcomed = true; api("/api/settings", { body: { welcomed: true } }); },

  /* ---------- Trung tâm Model ---------- */
  async openModels() {
    const [st, cat] = await Promise.all([api("/api/engine/status?gpu=1"), api("/api/engine/catalog")]);
    this.mc = { st, catalog: cat.catalog, local: cat.local, gpu: st.gpu };
    this.modal(`<div class="mc">
      <div class="mc-head"><h3>🧠 Model AI</h3><button class="mini" onclick="App.closeModal()" title="Đóng">✕</button></div>
      <div class="mc-status" id="mcStatus"></div>
      <h4>Model đề xuất <span class="note">– đã gỡ kiểm duyệt, viết được truyện 18+ / NSFW</span></h4>
      <div class="mc-grid" id="mcCat"></div>
      <h4>Model trên máy</h4>
      <div id="mcLocal"></div>
      <details class="mc-more"><summary>➕ Tải model khác từ HuggingFace / thêm thư mục model</summary>
        <div class="row" style="margin-top:10px">
          <input id="hfRepo" placeholder="tác-giả/tên-model-GGUF (hoặc dán link HuggingFace)" style="flex:1;min-width:260px">
          <select id="hfQuant"><option>Q4_K_M</option><option>Q5_K_M</option><option>Q6_K</option><option>Q8_0</option><option>IQ4_XS</option><option>Q3_K_M</option></select>
          <button class="primary" onclick="App.hfDownload()">⬇ Tải</button>
        </div>
        <div class="row" style="margin-top:10px">
          <input id="addDir" placeholder="Thư mục đang chứa file .gguf (VD: D:\\Models)" style="flex:1;min-width:260px">
          <button class="ghost-btn" onclick="App.pickDir()">📁 Chọn…</button>
          <button class="ghost-btn" onclick="App.addDir()">Thêm</button>
        </div>
        <p class="note">Model của LM Studio trên máy được tự nhận. Model tải về lưu tại: <code>${esc(st.models_dir)}</code></p>
      </details>
      <p class="note" style="margin-top:14px">Muốn dùng LM Studio / Ollama / KoboldCpp thay cho bộ máy có sẵn? <a href="#" onclick="App.closeModal();App.openSettings();return false">Mở Cài đặt</a>.</p>
    </div>`);
    $("#modal").classList.add("wide");
    $("#modal").onclick = e => {
      const r = e.target.closest("[data-run]"), d = e.target.closest("[data-delm]");
      if (r) this.runModel(r.dataset.run, r.dataset.name);
      if (d) this.delModel(d.dataset.delm);
    };
    this.renderMC();
    this.pollMC();
  },

  pollMC() {
    clearTimeout(this.mcTimer);
    this.mcTimer = setTimeout(async () => {
      if ($("#modalBg").classList.contains("hidden") || !$("#mcStatus")) { $("#modal").classList.remove("wide"); return; }
      const before = (this.mc.st.tasks || []).filter(t => t.state === "running").length;
      const st = await api("/api/engine/status").catch(() => null);
      if (st) {
        st.models_dir = this.mc.st.models_dir;
        const after = st.tasks.filter(t => t.state === "running").length;
        const changedEngine = st.engine.installed !== this.mc.st.engine.installed;
        this.mc.st = st;
        if (after < before || changedEngine) {
          const cat = await api("/api/engine/catalog");
          this.mc.catalog = cat.catalog; this.mc.local = cat.local;
          st.tasks.filter(t => t.state === "error").forEach(t => { if (!t._shown) toast(t.label + ": " + t.msg, true, 8000); });
        }
        this.renderMC();
        this.refreshModel();
      }
      this.pollMC();
    }, 1000);
  },

  taskFor(key) { return (this.mc.st.tasks || []).filter(t => t.key === key).sort((a, b) => b.started - a.started)[0]; },

  progressHTML(t) {
    const pct = t.total ? Math.min(100, t.done / t.total * 100) : 0;
    return `<div class="progress"><div style="width:${pct}%"></div></div>
      <div class="mc-prog"><span>${esc(t.msg)}</span><span>${t.total ? fmtGB(t.done) + " / " + fmtGB(t.total) + " · " + pct.toFixed(0) + "%" : ""}${t.speed ? " · " + fmtSpeed(t.speed) : ""}</span>
      <button class="mini" onclick="App.cancelTask('${t.id}')">Huỷ</button></div>`;
  },

  renderMC() {
    const { st, gpu } = this.mc, s = st.server, e = st.engine;
    const et = this.taskFor("engine");
    const vram = gpu ? gpu.total_mb / 1024 : 0;
    const stLabel = { ready: "🟢 Đang chạy", loading: "🟡 Đang nạp…", error: "🔴 Lỗi", stopped: "⚪ Chưa chạy" }[s.state] || s.state;
    $("#mcStatus").innerHTML = `
      <div class="mc-row"><b>Card đồ hoạ</b><span>${gpu ? esc(gpu.name) + " · " + vram.toFixed(0) + " GB VRAM (trống " + (gpu.free_mb / 1024).toFixed(1) + " GB)" : "Không thấy card NVIDIA"}</span></div>
      <div class="mc-row"><b>Bộ máy</b><span>${e.installed ? "✔ llama.cpp " + esc(e.version) + " · " + esc(e.backend) : "Chưa cài"}</span>
        ${et && et.state === "running" ? "" : `<select id="mcBackend" class="sm-sel" title="Loại bộ máy">
          ${[["cuda12", "NVIDIA CUDA 12"], ["cuda13", "NVIDIA CUDA 13"], ["vulkan", "Vulkan (AMD/Intel/NVIDIA)"], ["cpu", "Chỉ CPU"]].map(([v, l]) => `<option value="${v}" ${v === (e.backend || (gpu ? "cuda12" : "vulkan")) ? "selected" : ""}>${l}</option>`).join("")}
        </select><button class="ghost-btn sm" onclick="App.installEngine()">${e.installed ? "⟳ Cập nhật / cài lại" : "⬇ Cài bộ máy"}</button>
        <button class="ghost-btn sm" title="Đã tự tải gói llama.cpp (.zip) từ GitHub? Chọn file để cài" onclick="App.installEngineZip()">📦 Chọn file .zip</button>`}</div>
      ${et && et.state === "error" ? `<div class="note" style="color:var(--danger)">${esc(et.msg)}<br>Cách thủ công: mở <a href="#" onclick="App.openUrl('https://github.com/ggml-org/llama.cpp/releases');return false">trang llama.cpp</a>, tải 2 file <code>llama-…-bin-win-cuda-12.4-x64.zip</code> và <code>cudart-llama-bin-win-cuda-12.4-x64.zip</code>, rồi bấm “📦 Chọn file .zip” và chọn cả 2.</div>` : ""}
      ${et && et.state === "running" ? this.progressHTML(et) : ""}
      <div class="mc-row"><b>Model</b><span>${stLabel}${s.name && s.state !== "stopped" ? " · " + esc(s.name) : ""}</span>
        <label class="note" style="display:flex;gap:6px;align-items:center">Context
          <select id="mcCtx" onchange="App.setCtx(this.value)">${[8192, 12288, 16384, 24576, 32768, 49152].map(v => `<option value="${v}" ${v == (this.settings.engine_ctx || 16384) ? "selected" : ""}>${v / 1024}k</option>`).join("")}</select></label>
        ${s.state === "ready" || s.state === "loading" ? `<button class="ghost-btn sm" onclick="App.restartModel()">↻ Khởi động lại</button><button class="danger-btn sm" onclick="App.stopModel()">⏹ Dừng</button>` : ""}</div>
      ${s.state === "error" || (s.state === "loading" && s.msg) ? `<div class="note" style="color:${s.state === "error" ? "var(--danger)" : "inherit"}">${esc(s.msg)}</div>` : ""}`;

    $("#mcCat").innerHTML = this.mc.catalog.map(c => {
      const key = c.repo + ":" + c.quant, t = this.taskFor(key);
      const running = t && t.state === "running";
      const active = c.local_path && s.model && c.local_path === s.model && s.state !== "stopped";
      const fits = vram ? c.size_gb < vram - 1.6 : false;
      let act;
      if (running) act = this.progressHTML(t);
      else if (active) act = `<span class="ok-txt">${s.state === "ready" ? "● Đang dùng" : "Đang nạp…"}</span>`;
      else if (c.local_path) act = `<button class="primary sm" data-run="${esc(c.local_path)}" data-name="${esc(c.name)}">▶ Dùng model này</button>
          <button class="mini" title="Xoá file model" data-delm="${esc(c.local_path)}">🗑</button>`;
      else act = `<button class="primary sm" onclick="App.dlModel('${c.id}',true)">⬇ Tải & dùng</button>
          <button class="ghost-btn sm" onclick="App.dlModel('${c.id}',false)">Chỉ tải</button>
          ${t && t.state === "error" ? `<div class="note" style="color:var(--danger)">${esc(t.msg)}</div>` : ""}
          ${t && t.state === "cancelled" ? `<div class="note">Đã huỷ – bấm tải để tải tiếp phần còn lại</div>` : ""}`;
      return `<div class="mc-card ${c.featured ? "feat" : ""} ${active ? "active" : ""}">
        <div class="mc-title">${esc(c.name)}${c.featured ? ' <span class="tag rec">Đề xuất</span>' : ""}</div>
        <div class="mc-tags"><span class="tag">${c.lang === "vi" ? "🇻🇳 Tiếng Việt tốt" : "🇬🇧 Tiếng Anh"}</span><span class="tag r-nsfw">NSFW</span>
          <span class="tag">${c.size_gb} GB</span>${vram ? `<span class="tag ${fits ? "fit" : ""}">${fits ? "Vừa GPU" : "Tràn sang RAM"}</span>` : ""}</div>
        <p>${esc(c.desc)}</p><p class="note">⚡ ${esc(c.speed)}</p>
        <div class="mc-act">${act}</div></div>`;
    }).join("");

    const others = this.mc.local.filter(m => !m.catalog_id || !this.mc.catalog.some(c => c.id === m.catalog_id));
    const custom = (st.tasks || []).filter(t => t.kind === "model" && t.state === "running" && !this.mc.catalog.some(c => t.key === c.repo + ":" + c.quant));
    $("#mcLocal").innerHTML = custom.map(t => `<div class="mc-local"><b>${esc(t.label)}</b>${this.progressHTML(t)}</div>`).join("") +
      (others.length ? others.map(m => {
        const active = s.model === m.path && s.state !== "stopped";
        return `<div class="mc-local"><div><b>${esc(m.name)}</b><div class="note">${fmtGB(m.size)} · ${m.source === "lmstudio" ? "LM Studio" : m.source === "app" ? "tải trong app" : "thư mục thêm"} · ${esc(m.path)}</div></div>
          <div class="mc-act">${active ? '<span class="ok-txt">● Đang dùng</span>' : `<button class="primary sm" data-run="${esc(m.path)}" data-name="${esc(m.name)}">▶ Dùng</button>`}
          ${m.source === "app" ? `<button class="mini" title="Xoá" data-delm="${esc(m.path)}">🗑</button>` : ""}</div></div>`;
      }).join("") : (custom.length ? "" : `<p class="note">Chưa có model nào khác. Model trong danh sách đề xuất sau khi tải sẽ hiện ở thẻ phía trên.</p>`));
  },

  async installEngine() {
    const b = $("#mcBackend");
    const r = await api("/api/engine/install", { body: { backend: b ? b.value : undefined } });
    if (r.error) toast(r.error, true);
  },
  async installEngineZip() {
    const r = await api("/api/engine/install_files", { body: {} });
    if (r.cancelled) return;
    if (r.error) { toast(r.error, true, 8000); return; }
    toast("Đã cài bộ máy llama.cpp " + (r.engine.version || ""));
    this.openModels();
  },
  async dlModel(id, start) {
    const r = await api("/api/engine/download", { body: { id, start } });
    if (r.error) toast(r.error, true);
    else if (start && !this.mc.st.engine.installed) api("/api/engine/install", { body: {} });
  },
  async hfDownload() {
    const repo = $("#hfRepo").value.trim();
    if (!repo) { toast("Nhập tên repo HuggingFace, VD: bartowski/Mistral-Nemo-Instruct-2407-GGUF"); return; }
    const r = await api("/api/engine/download", { body: { repo, quant: $("#hfQuant").value } });
    if (r.error) toast(r.error, true); else toast("Đã bắt đầu tải " + repo);
  },
  async runModel(path, name) {
    if (!this.mc.st.engine.installed) {
      toast("Đang cài bộ máy chạy model trước…");
      await api("/api/engine/install", { body: {} });
      const wait = async () => {
        const st = await api("/api/engine/status");
        if (st.engine.installed) return api("/api/engine/start", { body: { path, name } });
        if (!st.tasks.some(t => t.kind === "engine" && t.state === "running")) { toast("Cài bộ máy thất bại", true); return; }
        setTimeout(wait, 1500);
      };
      return wait();
    }
    const r = await api("/api/engine/start", { body: { path, name } });
    if (r.error) toast(r.error, true);
    this.settings = (await api("/api/settings")).settings;
    this.refreshModel();
  },
  async stopModel() { await api("/api/engine/stop", { body: {} }); this.refreshModel(); },
  async restartModel() {
    const s = this.mc.st.server;
    if (s.model) await api("/api/engine/start", { body: { path: s.model, name: s.name, ctx: this.settings.engine_ctx } });
  },
  async setCtx(v) {
    this.settings.engine_ctx = +v;
    await api("/api/settings", { body: { engine_ctx: +v, context_chars: Math.round(+v * 1.8) } });
    this.settings.context_chars = Math.round(+v * 1.8);
    if (this.mc.st.server.state !== "stopped") toast("Bấm ↻ Khởi động lại để áp dụng context mới.");
  },
  async delModel(path) {
    if (!await this.confirm("Xoá file model này khỏi máy?", "Xoá", true)) { this.openModels(); return; }
    const r = await api("/api/engine/delete_model", { body: { path } });
    if (r.error) toast(r.error, true);
    this.openModels();
  },
  cancelTask(id) { api("/api/engine/cancel", { body: { task: id } }); },
  async pickDir() {
    const r = await api("/api/engine/pick_folder", { body: {} });
    if (r.path) $("#addDir").value = r.path; else if (r.error) toast(r.error);
  },
  async addDir() {
    const r = await api("/api/engine/add_folder", { body: { path: $("#addDir").value } });
    if (r.error) toast(r.error, true); else this.openModels();
  },
});

// Nút model trên thanh trên mở Trung tâm Model
$("#modelPill").onclick = () => (App.settings.provider || "builtin") === "builtin" ? App.openModels() : App.openSettings();
const _closeModal = App.closeModal.bind(App);
App.closeModal = function () { $("#modal").classList.remove("wide"); $("#modal").onclick = null; _closeModal(); };

(async () => { await App.init(); App.maybeWelcome(); })();
