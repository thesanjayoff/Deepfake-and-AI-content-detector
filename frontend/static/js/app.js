(() => {
  const viewRoot = document.getElementById("view-root");
  const modalRoot = document.getElementById("modal-root");
  const toastRoot = document.getElementById("toast-root");
  let currentRoute = "analyze";
  let openReportId = null; // when set, history/compare show the detail view instead of the list

  // ---------- Toast ----------
  function toast(message, isError = false) {
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " error" : "");
    el.textContent = message;
    toastRoot.appendChild(el);
    setTimeout(() => el.remove(), 4500);
  }

  // ---------- Theme ----------
  function initTheme() {
    const saved = localStorage.getItem("daicd-theme") || "dark";
    document.documentElement.setAttribute("data-theme", saved);
    document.getElementById("theme-toggle").textContent = saved === "dark" ? "🌙" : "☀️";
  }
  function toggleTheme() {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("daicd-theme", next);
    document.getElementById("theme-toggle").textContent = next === "dark" ? "🌙" : "☀️";
  }

  // ---------- Modal ----------
  function openModal(innerHtml) {
    modalRoot.innerHTML = innerHtml;
    modalRoot.classList.remove("hidden");
    modalRoot.querySelectorAll("[data-close]").forEach(b => b.addEventListener("click", closeModal));
    modalRoot.addEventListener("click", (e) => { if (e.target === modalRoot) closeModal(); }, { once: true });
  }
  function closeModal() { modalRoot.classList.add("hidden"); modalRoot.innerHTML = ""; }

  // ---------- Routing ----------
  function setRoute(route) {
    currentRoute = route;
    openReportId = null;
    document.querySelectorAll(".nav-btn").forEach(b => b.classList.toggle("active", b.dataset.route === route));
    render();
  }

  function render() {
    if (currentRoute === "analyze") return renderAnalyze();
    if (currentRoute === "history") return openReportId ? renderReportDetail(openReportId, "history") : renderHistory();
    if (currentRoute === "compare") return renderCompare();
    if (currentRoute === "settings") return renderSettings();
  }

  // ---------- Analyze ----------
  const pendingUploads = []; // {file, reference, el, status}

  function renderAnalyze() {
    viewRoot.innerHTML = `
      <h1>Analyze a file</h1>
      <p>Drop one or more images, audio clips, videos, or text files. Each is analyzed locally and independently.</p>
      <div class="card">
        <div class="dropzone" id="dropzone">
          <div class="dropzone-icon">⬆️</div>
          <div>Drag &amp; drop files here, or click to choose</div>
          <div class="dropzone-sub">Images, audio (wav/mp3/ogg/opus/m4a), video (mp4/mov/webm/mkv), or .txt</div>
          <input type="file" id="file-input" multiple hidden
            accept=".jpg,.jpeg,.png,.webp,.bmp,.tiff,.gif,.wav,.flac,.ogg,.opus,.mp3,.m4a,.aac,.3gp,.mp4,.mov,.webm,.mkv,.avi,.txt" />
        </div>
        <div class="field" style="margin-top:16px">
          <label for="tags-input">Tags (comma separated, optional)</label>
          <input id="tags-input" placeholder="e.g. family, work, suspicious-call" />
        </div>
        <div class="field">
          <label for="reference-input">Reference voice clip (optional -- only used for audio speaker comparison)</label>
          <input type="file" id="reference-input" accept=".wav,.flac,.ogg,.opus,.mp3,.m4a,.aac,.3gp" />
          <p class="muted">Only use a reference clip you have the right to use (e.g. your own relative/colleague, with consent).</p>
        </div>
        <div id="file-progress" class="file-progress-list"></div>
      </div>
      <div id="results"></div>
    `;

    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("file-input");
    dropzone.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("drag-over"); });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("drag-over");
      handleFiles([...e.dataTransfer.files]);
    });
    fileInput.addEventListener("change", () => handleFiles([...fileInput.files]));
  }

  async function handleFiles(files) {
    if (!files.length) return;
    const tags = document.getElementById("tags-input").value;
    const referenceInput = document.getElementById("reference-input");
    const reference = referenceInput.files[0] || null;
    const progressContainer = document.getElementById("file-progress");
    const resultsContainer = document.getElementById("results");

    for (const file of files) {
      const row = document.createElement("div");
      row.className = "file-progress-item";
      row.innerHTML = `
        <span class="fname">${Render.escapeHtml(file.name)}</span>
        <div class="progress-bar"><div></div></div>
        <span class="status-pill pending">queued</span>
      `;
      progressContainer.appendChild(row);
      const bar = row.querySelector(".progress-bar > div");
      const pill = row.querySelector(".status-pill");

      pill.textContent = "analyzing"; pill.className = "status-pill working";
      try {
        const record = await Api.analyze(file, {
          reference, tags,
          onProgress: (pct) => { bar.style.width = pct + "%"; },
        });
        pill.textContent = "done"; pill.className = "status-pill done";
        bar.style.width = "100%";

        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `<h2>${Render.escapeHtml(file.name)}</h2>` + Render.fullReport(record);
        resultsContainer.prepend(card);
        Render.attachSignalToggles(card);
        toast(`Analysis complete for ${file.name}`);
      } catch (err) {
        pill.textContent = "error"; pill.className = "status-pill error";
        row.title = err.message;
        toast(`${file.name}: ${err.message}`, true);
      }
    }
  }

  // ---------- History ----------
  async function renderHistory() {
    viewRoot.innerHTML = `
      <h1>History</h1>
      <div class="history-toolbar">
        <input id="search-input" placeholder="Search by filename or verdict... (press / to focus)" />
        <select id="media-filter">
          <option value="">All media types</option>
          <option value="image">Image</option>
          <option value="audio">Audio</option>
          <option value="video">Video</option>
          <option value="text">Text</option>
        </select>
        <input id="tag-filter" placeholder="Filter by tag" style="max-width:160px" />
      </div>
      <div id="history-list" class="history-list"><p class="muted">Loading...</p></div>
    `;
    const searchInput = document.getElementById("search-input");
    const mediaFilter = document.getElementById("media-filter");
    const tagFilter = document.getElementById("tag-filter");
    const reload = () => loadHistoryList(searchInput.value, tagFilter.value, mediaFilter.value);
    searchInput.addEventListener("input", debounce(reload, 250));
    tagFilter.addEventListener("input", debounce(reload, 250));
    mediaFilter.addEventListener("change", reload);
    reload();
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  async function loadHistoryList(q, tag, mediaType) {
    const listEl = document.getElementById("history-list");
    try {
      const rows = await Api.listReports({ q, tag, mediaType });
      if (!rows.length) {
        listEl.innerHTML = `<div class="empty-state">No reports yet. Analyze a file to get started.</div>`;
        return;
      }
      listEl.innerHTML = rows.map(r => `
        <div class="history-row" data-id="${r.id}">
          <span class="verdict-dot ${Render.escapeHtml(r.verdict)}"></span>
          <span class="media-icon">${Render.MEDIA_ICON[r.media_type] || "📎"}</span>
          <div class="title">
            <div class="fname">${Render.escapeHtml(r.original_name)}</div>
            <div class="sub">${new Date(r.created_at).toLocaleString()} &middot; ${Render.escapeHtml(Render.VERDICT_LABEL[r.verdict] || r.verdict)} ${Render.tagChips(r.tags)}</div>
          </div>
          <button class="btn secondary delete-btn" data-id="${r.id}">Delete</button>
        </div>
      `).join("");
      listEl.querySelectorAll(".history-row").forEach(row => {
        row.addEventListener("click", (e) => {
          if (e.target.closest(".delete-btn")) return;
          openReportId = row.dataset.id;
          render();
        });
      });
      listEl.querySelectorAll(".delete-btn").forEach(btn => {
        btn.addEventListener("click", async (e) => {
          e.stopPropagation();
          if (!confirm("Delete this report and its evidence files? This cannot be undone.")) return;
          try {
            await Api.deleteReport(btn.dataset.id);
            toast("Report deleted");
            loadHistoryList(q, tag, mediaType);
          } catch (err) { toast(err.message, true); }
        });
      });
    } catch (err) {
      listEl.innerHTML = `<div class="empty-state">Failed to load history: ${Render.escapeHtml(err.message)}</div>`;
    }
  }

  async function renderReportDetail(id, backRoute) {
    viewRoot.innerHTML = `<p class="muted">Loading report...</p>`;
    try {
      const record = await Api.getReport(id);
      viewRoot.innerHTML = `
        <button class="btn secondary" id="back-btn">&larr; Back</button>
        <div class="card" style="margin-top:14px">
          <h1>${Render.escapeHtml(record.original_name)}</h1>
          ${Render.fullReport(record)}
        </div>
      `;
      Render.attachSignalToggles(viewRoot);
      document.getElementById("back-btn").addEventListener("click", () => { openReportId = null; render(); });
    } catch (err) {
      viewRoot.innerHTML = `<div class="empty-state">Could not load report: ${Render.escapeHtml(err.message)}</div>`;
    }
  }

  // ---------- Compare ----------
  async function renderCompare() {
    viewRoot.innerHTML = `<h1>Compare two reports</h1><p class="muted">Loading reports...</p>`;
    let rows = [];
    try { rows = await Api.listReports({}); } catch (err) { toast(err.message, true); }

    const options = rows.map(r => `<option value="${r.id}">${Render.escapeHtml(r.original_name)} (${new Date(r.created_at).toLocaleDateString()})</option>`).join("");

    viewRoot.innerHTML = `
      <h1>Compare two reports</h1>
      <p>Pick two previously analyzed items -- e.g. an original photo and a version you suspect was edited.</p>
      <div class="grid-2">
        <div class="field"><label>Item A</label><select id="compare-a"><option value="">Select...</option>${options}</select></div>
        <div class="field"><label>Item B</label><select id="compare-b"><option value="">Select...</option>${options}</select></div>
      </div>
      <div id="compare-output" class="compare-grid"></div>
    `;
    const refresh = async () => {
      const a = document.getElementById("compare-a").value;
      const b = document.getElementById("compare-b").value;
      const out = document.getElementById("compare-output");
      out.innerHTML = "";
      if (a) out.innerHTML += `<div class="card" id="compare-a-card"><p class="muted">Loading...</p></div>`;
      if (b) out.innerHTML += `<div class="card" id="compare-b-card"><p class="muted">Loading...</p></div>`;
      if (a) {
        const rec = await Api.getReport(a);
        document.getElementById("compare-a-card").innerHTML = `<h2>${Render.escapeHtml(rec.original_name)}</h2>` + Render.fullReport(rec);
        Render.attachSignalToggles(document.getElementById("compare-a-card"));
      }
      if (b) {
        const rec = await Api.getReport(b);
        document.getElementById("compare-b-card").innerHTML = `<h2>${Render.escapeHtml(rec.original_name)}</h2>` + Render.fullReport(rec);
        Render.attachSignalToggles(document.getElementById("compare-b-card"));
      }
    };
    document.getElementById("compare-a").addEventListener("change", refresh);
    document.getElementById("compare-b").addEventListener("change", refresh);
  }

  // ---------- Settings ----------
  async function renderSettings() {
    viewRoot.innerHTML = `<h1>Settings</h1><p class="muted">Loading...</p>`;
    let settings = {};
    try { settings = await Api.getSettings(); } catch (err) { toast(err.message, true); }

    const row = (key, title, desc) => `
      <div class="toggle-row">
        <div><div>${title}</div><div class="desc">${desc}</div></div>
        <label class="switch">
          <input type="checkbox" data-setting="${key}" ${settings[key] === "true" ? "checked" : ""} />
          <span class="slider"></span>
        </label>
      </div>`;

    viewRoot.innerHTML = `
      <h1>Settings</h1>
      <div class="card">
        <h2>Privacy &amp; models</h2>
        ${row("fully_local_mode", "Fully local mode", "Blocks any optional model download/network lookup. Recommended default.")}
        ${row("use_optional_ml_models", "Use optional ML models", "Enables the Hugging Face AI-image detector and GPT-2 text perplexity signal, if the ML extras are installed (see README). Downloads model weights on first use.")}
        ${row("delete_uploads_after_analysis", "Delete uploaded files after analysis", "Keeps the report and evidence images, but removes the original uploaded file from disk once analysis finishes.")}
      </div>
      <div class="card">
        <h2>Appearance</h2>
        <div class="toggle-row">
          <div><div>Dark mode</div><div class="desc">Toggle with the 🌙/☀️ button in the top bar, or press 't'.</div></div>
          <label class="switch">
            <input type="checkbox" id="theme-switch" ${document.documentElement.getAttribute("data-theme") === "dark" ? "checked" : ""} />
            <span class="slider"></span>
          </label>
        </div>
      </div>
      <div class="card">
        <h2>About</h2>
        <p>This app runs entirely on your machine. Nothing is uploaded anywhere unless you explicitly click a reverse-image-search link, which opens your own browser -- this app never sends your files anywhere itself.</p>
        <p class="muted">Results are evidence to help you judge content. They are not proof, and "Inconclusive" is a normal, common result.</p>
      </div>
    `;
    viewRoot.querySelectorAll("input[data-setting]").forEach(input => {
      input.addEventListener("change", async () => {
        try {
          await Api.updateSettings({ [input.dataset.setting]: input.checked });
          toast("Setting saved");
        } catch (err) { toast(err.message, true); input.checked = !input.checked; }
      });
    });
    document.getElementById("theme-switch").addEventListener("change", toggleTheme);
  }

  // ---------- Keyboard shortcuts ----------
  function initShortcuts() {
    document.addEventListener("keydown", (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") {
        if (e.key === "Escape") e.target.blur();
        return;
      }
      if (!modalRoot.classList.contains("hidden") && e.key === "Escape") { closeModal(); return; }
      if (openReportId && e.key === "Escape") { openReportId = null; render(); return; }
      if (e.key === "t") { toggleTheme(); return; }
      if (e.key === "?") { showShortcutsModal(); return; }
      if (e.key === "1") { setRoute("analyze"); return; }
      if (e.key === "2") { setRoute("history"); return; }
      if (e.key === "3") { setRoute("compare"); return; }
      if (e.key === "4") { setRoute("settings"); return; }
      if (e.key === "u" && currentRoute === "analyze") { document.getElementById("file-input")?.click(); return; }
      if (e.key === "/" && currentRoute === "history") {
        e.preventDefault();
        document.getElementById("search-input")?.focus();
        return;
      }
    });
  }

  function showShortcutsModal() {
    const tmpl = document.getElementById("tmpl-shortcuts");
    openModal(tmpl.innerHTML);
  }

  // ---------- Init ----------
  function init() {
    initTheme();
    document.querySelectorAll(".nav-btn").forEach(b => b.addEventListener("click", () => setRoute(b.dataset.route)));
    document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
    document.getElementById("shortcuts-btn").addEventListener("click", showShortcutsModal);
    initShortcuts();
    Api.health().catch(() => toast("Could not reach the local backend. Is it running?", true));
    render();
  }

  init();
})();
