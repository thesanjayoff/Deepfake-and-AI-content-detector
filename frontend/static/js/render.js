// Rendering helpers. Every piece of dynamic text here may ultimately come
// from an untrusted uploaded file (EXIF software tags, C2PA signer names,
// encoder tags, the text content itself) -- so EVERYTHING dynamic goes
// through escapeHtml() before landing in innerHTML. Never interpolate a
// backend string into a template without escaping it first.
const Render = (() => {
  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  const VERDICT_LABEL = {
    likely_authentic: "Likely Authentic",
    inconclusive: "Inconclusive",
    likely_manipulated: "Likely Manipulated or AI-Generated",
  };
  const MEDIA_ICON = { image: "🖼️", audio: "🎙️", video: "🎞️", text: "📄" };

  function verdictBanner(combination) {
    const verdict = combination.verdict;
    const label = VERDICT_LABEL[verdict] || verdict;
    const leanPct = ((combination.lean_score + 1) / 2) * 100;
    return `
      <div class="verdict-banner ${escapeHtml(verdict)}">
        <div style="flex:1">
          <div class="verdict-title">${escapeHtml(label)}</div>
          <div class="verdict-band">Confidence band: ${escapeHtml(combination.confidence_band)}</div>
          <div class="verdict-explanation">${escapeHtml(combination.explanation)}</div>
          <div class="lean-bar-wrap">
            <div class="lean-bar-label">
              <span>Leans authentic</span><span>Not a probability -- see signals below</span><span>Leans manipulated</span>
            </div>
            <div class="lean-bar"><div class="lean-bar-marker" style="left:${leanPct}%"></div></div>
          </div>
        </div>
      </div>`;
  }

  function qualityWarnings(warnings) {
    if (!warnings || !warnings.length) return "";
    return `<div class="section-title">Quality warnings (lower reliability)</div>` +
      warnings.map(w => `<div class="quality-warning">⚠ ${escapeHtml(w.message)}</div>`).join("");
  }

  function signalBadgeColor(direction) {
    if (direction >= 0.25) return "var(--manipulated)";
    if (direction <= -0.25) return "var(--authentic)";
    return "var(--inconclusive)";
  }

  function signalList(signals) {
    if (!signals || !signals.length) return "<p class=\"muted\">No signals.</p>";
    return `<div class="signal-list">` + signals.map((s, i) => {
      const na = !s.applicable && s.strength === 0;
      const color = signalBadgeColor(s.direction);
      return `
      <div class="signal-item ${na ? "not-applicable" : ""}" data-signal-idx="${i}">
        <div class="signal-head">
          <span class="chevron">▸</span>
          <span class="signal-label">${escapeHtml(s.label)}</span>
          <span class="signal-badge">${escapeHtml(s.category)}</span>
          <div class="signal-strength-bar"><div style="width:${Math.round(s.strength * 100)}%; background:${color}"></div></div>
        </div>
        <div class="signal-summary">${escapeHtml(s.summary)}</div>
        <div class="signal-limits"><b>Known limits:</b> ${escapeHtml(s.limits)}</div>
      </div>`;
    }).join("") + `</div>`;
  }

  function attachSignalToggles(root) {
    root.querySelectorAll(".signal-head").forEach(head => {
      head.addEventListener("click", () => {
        head.closest(".signal-item").classList.toggle("expanded");
      });
    });
  }

  function evidenceGrid(evidence, reportId) {
    if (!evidence || !Object.keys(evidence).length) return "";
    const captions = {
      ela_heatmap: "Error Level Analysis heatmap",
      noise_heatmap: "Noise residual heatmap",
      ghost_heatmap: "Double-compression ('ghost') map",
      copymove_overlay: "Copy-move keypoint matches",
      spectrogram: "Audio spectrogram",
      audio_spectrogram: "Extracted audio track spectrogram",
      frame_thumbnail: "Sample video frame",
    };
    return `<div class="section-title">Visual evidence</div><div class="evidence-grid">` +
      Object.entries(evidence).map(([key, filename]) => `
        <div class="evidence-item">
          <img src="${Api.evidenceUrl(reportId, filename)}" alt="${escapeHtml(captions[key] || key)}" loading="lazy" />
          <div class="evidence-caption">${escapeHtml(captions[key] || key)}</div>
        </div>`).join("") + `</div>`;
  }

  function timelineChart(timeline) {
    if (!timeline || !timeline.length) return "";
    const scores = timeline.map(t => t.frame_score || 0);
    const mean = scores.reduce((a, b) => a + b, 0) / (scores.length || 1);
    const std = Math.sqrt(scores.reduce((a, b) => a + (b - mean) ** 2, 0) / (scores.length || 1));
    return `<div class="section-title">Per-frame forensic timeline</div>
      <div class="timeline-chart">` +
      timeline.map(t => {
        const hot = t.frame_score > mean + 2 * std && t.frame_score > 0.3;
        const h = Math.max(2, Math.round((t.frame_score || 0) * 70));
        return `<div class="timeline-bar ${hot ? "hot" : ""}" style="height:${h}px" title="t=${t.t.toFixed(2)}s score=${t.frame_score.toFixed(2)}${t.face_detected ? " (face)" : ""}"></div>`;
      }).join("") + `</div><div class="muted">Each bar is a sampled frame; red bars are statistical outliers worth a closer look.</div>`;
  }

  function verificationSteps(steps) {
    if (!steps || !steps.length) return "";
    return `<div class="section-title">Recommended human verification steps</div>
      <ul class="checklist">${steps.map(s => `<li>${escapeHtml(s)}</li>`).join("")}</ul>`;
  }

  function scamChecklist(items, safeWordTip) {
    if (!items) return "";
    return `<div class="section-title">Voice-clone / scam-call checklist</div>
      <ul class="checklist">${items.map(s => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
      <p class="muted">${escapeHtml(safeWordTip || "")}</p>`;
  }

  function tagChips(tags) {
    if (!tags || !tags.length) return "";
    return tags.map(t => `<span class="tag-chip">${escapeHtml(t)}</span>`).join("");
  }

  function mandatoryWarning(text) {
    if (!text) return "";
    return `<div class="warning-banner">⚠ ${escapeHtml(text)}</div>`;
  }

  function textPreview(preview) {
    if (!preview) return "";
    return `<div class="section-title">Text preview</div>
      <div class="card text-mono" style="white-space:pre-wrap; max-height:260px; overflow:auto">${escapeHtml(preview)}</div>`;
  }

  function fullReport(record) {
    const report = record.report;
    const mediaLine = `${MEDIA_ICON[record.media_type] || "📎"} ${escapeHtml(record.media_type)} &middot; ${escapeHtml(record.original_name)} &middot; ${(record.size_bytes / 1024).toFixed(1)} KB`;
    let extra = "";
    if (report.media_type === "text") extra = mandatoryWarning(report.mandatory_warning);

    let specifics = "";
    if (report.timeline) specifics += timelineChart(report.timeline);
    if (report.scam_call_checklist) specifics += scamChecklist(report.scam_call_checklist, report.safe_word_guidance);
    if (report.text_preview) specifics += textPreview(report.text_preview);
    if (report.robustness_note) {
      specifics += `<div class="section-title">Robustness note</div>` +
        report.robustness_note.notes.map(n => `<p class="muted">${escapeHtml(n)}</p>`).join("");
    }

    return `
      <div class="muted" style="margin-bottom:10px">${mediaLine}</div>
      ${extra}
      ${verdictBanner(report.combination)}
      ${qualityWarnings(report.quality_warnings)}
      <div class="section-title">Provenance &amp; signals</div>
      ${signalList(report.signals)}
      ${evidenceGrid(report.evidence, record.id)}
      ${specifics}
      ${verificationSteps(report.verification_steps)}
      <div class="btn-row" style="margin-top:18px">
        <a class="btn secondary" href="${Api.exportJsonUrl(record.id)}" download>Export JSON</a>
        <a class="btn secondary" href="${Api.exportPdfUrl(record.id)}" download>Export PDF</a>
      </div>
    `;
  }

  return {
    escapeHtml, verdictBanner, qualityWarnings, signalList, attachSignalToggles,
    evidenceGrid, timelineChart, verificationSteps, scamChecklist, tagChips,
    mandatoryWarning, textPreview, fullReport, VERDICT_LABEL, MEDIA_ICON,
  };
})();
