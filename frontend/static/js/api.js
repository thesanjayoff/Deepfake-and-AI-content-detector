// Thin wrappers around the local-only backend API. Everything here talks to
// 127.0.0.1 only -- there are no calls to any third-party service.
const Api = (() => {
  const BASE = "/api";

  async function handle(resp) {
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const data = await resp.json();
        detail = data.detail || JSON.stringify(data);
      } catch (_) {}
      throw new Error(detail || `HTTP ${resp.status}`);
    }
    return resp;
  }

  return {
    async health() {
      return (await handle(await fetch(`${BASE}/health`))).json();
    },
    async getSettings() {
      return (await handle(await fetch(`${BASE}/settings`))).json();
    },
    async updateSettings(partial) {
      return (await handle(await fetch(`${BASE}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(partial),
      }))).json();
    },
    async analyze(file, { reference = null, tags = "", onProgress = null } = {}) {
      const form = new FormData();
      form.append("file", file, file.name);
      if (reference) form.append("reference", reference, reference.name);
      form.append("tags", tags);

      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${BASE}/analyze`);
        xhr.upload.onprogress = (e) => {
          if (onProgress && e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 60));
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            if (onProgress) onProgress(100);
            resolve(JSON.parse(xhr.responseText));
          } else {
            let detail = xhr.statusText;
            try { detail = JSON.parse(xhr.responseText).detail || detail; } catch (_) {}
            reject(new Error(detail));
          }
        };
        xhr.onerror = () => reject(new Error("Network error -- is the backend running?"));
        if (onProgress) onProgress(5);
        xhr.send(form);
      });
    },
    async listReports({ q = "", tag = "", mediaType = "" } = {}) {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (tag) params.set("tag", tag);
      if (mediaType) params.set("media_type", mediaType);
      return (await handle(await fetch(`${BASE}/reports?${params}`))).json();
    },
    async getReport(id) {
      return (await handle(await fetch(`${BASE}/reports/${id}`))).json();
    },
    async deleteReport(id) {
      return (await handle(await fetch(`${BASE}/reports/${id}`, { method: "DELETE" }))).json();
    },
    exportJsonUrl(id) { return `${BASE}/reports/${id}/export.json`; },
    exportPdfUrl(id) { return `${BASE}/reports/${id}/export.pdf`; },
    evidenceUrl(reportId, filename) { return `${BASE}/evidence/${reportId}/${filename}`; },
  };
})();
