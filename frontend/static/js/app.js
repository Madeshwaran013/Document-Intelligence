const API_BASE = "/api/v1";

let allDocuments = [];
let activeFilter = "all";
let searchQuery = "";

// Health Check & System Status
async function checkHealth() {
  const badge = document.getElementById("health-badge");
  const text = document.getElementById("health-text");
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) {
      badge.className = "health-badge online";
      text.textContent = "API Online";
    } else {
      throw new Error("API status not ok");
    }
  } catch (e) {
    badge.className = "health-badge offline";
    text.textContent = "API Offline";
  }
}

// Format Status Badges
function statusBadge(status) {
  const cls = status === "PASS" ? "badge-pass" : status === "FAILED" || status === "FAIL" ? "badge-fail" : "badge-na";
  return `<span class="badge ${cls}"><span style="font-size:10px">${status === "PASS" ? "●" : "▲"}</span> ${status}</span>`;
}

// Compute Metrics Summary Bar
function updateMetrics(docs) {
  const totalEl = document.getElementById("stat-total");
  const passRateEl = document.getElementById("stat-pass-rate");
  const avgTimeEl = document.getElementById("stat-avg-time");
  const engineEl = document.getElementById("stat-engine");

  if (!docs || docs.length === 0) {
    totalEl.textContent = "0";
    passRateEl.textContent = "100%";
    avgTimeEl.textContent = "-- ms";
    return;
  }

  totalEl.textContent = docs.length;

  const passed = docs.filter(d => d.processing_status === "PASS").length;
  const rate = Math.round((passed / docs.length) * 100);
  passRateEl.textContent = `${rate}%`;

  const times = docs.map(d => d.processing_metadata?.processing_time_ms).filter(Boolean);
  if (times.length > 0) {
    const avg = Math.round(times.reduce((a, b) => a + b, 0) / times.length);
    avgTimeEl.textContent = `${avg} ms`;
  }

  const hasLLM = docs.some(d => d.processing_metadata?.extraction_method === "llm");
  engineEl.textContent = hasLLM ? "Claude LLM" : "Heuristic OCR";
}

// Filter and Render Table
function filterAndRenderDocs() {
  const tbody = document.getElementById("doc-table-body");
  
  let filtered = allDocuments;
  
  if (activeFilter !== "all") {
    filtered = filtered.filter(doc => doc.document_type === activeFilter);
  }

  if (searchQuery.trim() !== "") {
    const q = searchQuery.toLowerCase();
    filtered = filtered.filter(doc => 
      doc.document_name.toLowerCase().includes(q) || 
      doc.document_type.toLowerCase().includes(q)
    );
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">No matching documents found.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map((doc) => `
    <tr>
      <td><strong style="color:var(--text-primary)">${escapeHtml(doc.document_name)}</strong></td>
      <td><span style="font-size:12px;background:rgba(30,41,59,0.5);padding:4px 8px;border-radius:4px;border:1px solid var(--panel-border);text-transform:capitalize">${escapeHtml(doc.document_type.replace(/_/g, " "))}</span></td>
      <td>${statusBadge(doc.processing_status)}</td>
      <td>${statusBadge(doc.validation?.overall_status || "NOT_APPLICABLE")}</td>
      <td style="color:var(--text-secondary);font-size:13px">${new Date(doc.created_at || Date.now()).toLocaleString()}</td>
      <td>
        <div style="display:flex;gap:8px">
          <a class="link-btn" href="/document/${encodeURIComponent(doc.document_name)}">Inspect Result →</a>
        </div>
      </td>
    </tr>
  `).join("");
}

// Fetch Document History
async function loadDocuments() {
  const tbody = document.getElementById("doc-table-body");
  try {
    const res = await fetch(`${API_BASE}/documents`);
    const data = await res.json();
    allDocuments = data.items || [];
    updateMetrics(allDocuments);
    filterAndRenderDocs();
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">Failed to load documents: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// UI Event Handlers: Document Type Chips
document.querySelectorAll(".type-chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".type-chip").forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    document.getElementById("document_type").value = chip.dataset.type;
  });
});

// Drag & Drop File Handling
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file");
const fileInfo = document.getElementById("file-info");
const selectedFilename = document.getElementById("selected-filename");
const removeFileBtn = document.getElementById("remove-file");
const processBtn = document.getElementById("process-btn");

dropZone.addEventListener("click", () => fileInput.click());

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  if (e.dataTransfer.files.length > 0) {
    fileInput.files = e.dataTransfer.files;
    handleFileSelected();
  }
});

fileInput.addEventListener("change", handleFileSelected);

function handleFileSelected() {
  if (fileInput.files.length > 0) {
    const file = fileInput.files[0];
    selectedFilename.textContent = `📄 ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    fileInfo.classList.remove("hidden");
    dropZone.classList.add("hidden");
    processBtn.disabled = false;
  }
}

removeFileBtn.addEventListener("click", () => {
  fileInput.value = "";
  fileInfo.classList.add("hidden");
  dropZone.classList.remove("hidden");
  processBtn.disabled = true;
});

// Form Submission
document.getElementById("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const docType = document.getElementById("document_type").value;
  const statusEl = document.getElementById("upload-status");

  if (!fileInput.files.length) return;

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("document_type", docType);

  processBtn.disabled = true;
  processBtn.innerHTML = `<span style="animation:pulse 1s infinite">⚙️ Processing OCR & Formulas...</span>`;
  statusEl.innerHTML = `<div style="padding:12px;background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.3);border-radius:8px;color:#a5b4fc;font-size:14px">Processing document with ${docType.replace(/_/g, " ")} pipeline...</div>`;

  try {
    const res = await fetch(`${API_BASE}/documents/process`, { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) {
      const msg = data?.error?.message || "Processing failed.";
      statusEl.innerHTML = `<div style="padding:12px;background:rgba(244,63,94,0.1);border:1px solid rgba(244,63,94,0.3);border-radius:8px;color:#f43f5e;font-size:14px">❌ Processing Error: ${escapeHtml(msg)}</div>`;
    } else {
      statusEl.innerHTML = `
        <div style="padding:16px;background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.3);border-radius:8px;color:#10b981;display:flex;justify-content:space-between;align-items:center">
          <div>
            <strong>Successfully Processed "${escapeHtml(data.document_name)}"!</strong>
            <div style="font-size:12px;color:var(--text-secondary);margin-top:4px">Status: ${data.processing_status} | Validation: ${data.validation?.overall_status || 'N/A'}</div>
          </div>
          <a href="/document/${encodeURIComponent(data.document_name)}" class="btn-secondary" style="color:#10b981;border-color:rgba(16,185,129,0.4)">Inspect Result →</a>
        </div>
      `;
      fileInput.value = "";
      fileInfo.classList.add("hidden");
      dropZone.classList.remove("hidden");
      loadDocuments();
    }
  } catch (err) {
    statusEl.innerHTML = `<div style="padding:12px;background:rgba(244,63,94,0.1);border:1px solid rgba(244,63,94,0.3);border-radius:8px;color:#f43f5e;font-size:14px">❌ Network Error: ${escapeHtml(err.message)}</div>`;
  } finally {
    processBtn.disabled = true;
    processBtn.innerHTML = `<span>Extract & Reconcile Document</span>`;
  }
});

// Search & Filter Listeners
document.getElementById("search-input").addEventListener("input", (e) => {
  searchQuery = e.target.value;
  filterAndRenderDocs();
});

document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeFilter = btn.dataset.filter;
    filterAndRenderDocs();
  });
});

document.getElementById("refresh-btn").addEventListener("click", loadDocuments);

checkHealth();
loadDocuments();
