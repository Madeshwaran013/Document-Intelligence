const API_BASE = "/api/v1";

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function getDocNameFromUrl() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 1]);
}

function statusBadge(status) {
  const cls = status === "PASS" ? "badge-pass" : status === "FAILED" || status === "FAIL" ? "badge-fail" : "badge-na";
  return `<span class="badge ${cls}"><span style="font-size:10px">${status === "PASS" ? "●" : "▲"}</span> ${status}</span>`;
}

function renderSummary(data) {
  document.getElementById("doc-title").textContent = data.document_name;
  
  const meta = document.getElementById("doc-meta");
  meta.innerHTML = `
    <span class="meta-item">📁 Type: <strong>${escapeHtml(data.document_type.replace(/_/g, " "))}</strong></span>
    <span class="meta-item">🤖 Method: <strong>${escapeHtml(data.processing_metadata?.extraction_method || 'heuristic')}</strong></span>
    <span class="meta-item">🔍 OCR Used: <strong>${data.processing_metadata?.ocr_used ? 'Yes' : 'No'}</strong></span>
    <span class="meta-item">⚡ Time: <strong>${data.processing_metadata?.processing_time_ms || 0} ms</strong></span>
  `;

  document.getElementById("doc-status-badge").innerHTML = `
    <div style="text-align:right">
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px">Pipeline Status</div>
      ${statusBadge(data.processing_status)}
    </div>
  `;
}

function renderFileValidation(fv) {
  const container = document.getElementById("file-validation");
  if (!fv) { container.innerHTML = `<p class="empty">File validation data unavailable.</p>`; return; }
  
  container.innerHTML = `
    <div class="field-grid">
      <div class="field-card">
        <div class="label">MIME Type</div>
        <div class="value" style="font-family:'JetBrains Mono',monospace;font-size:14px">${escapeHtml(fv.file_type)}</div>
      </div>
      <div class="field-card">
        <div class="label">Page Count</div>
        <div class="value">${escapeHtml(fv.page_count)} page(s)</div>
      </div>
      <div class="field-card">
        <div class="label">File Integrity</div>
        <div class="value" style="margin-top:4px">${statusBadge(fv.status)}</div>
      </div>
      ${fv.reason ? `
        <div class="field-card missing" style="grid-column:1/-1">
          <div class="label">Rejection Reason</div>
          <div class="value">${escapeHtml(fv.reason)}</div>
        </div>
      ` : ""}
    </div>
  `;
}

function renderExtractedFields(extracted) {
  const container = document.getElementById("extracted-fields");
  if (!extracted || Object.keys(extracted).length === 0) {
    container.innerHTML = `<p class="empty">No key-value fields extracted.</p>`;
    return;
  }
  const cards = [];
  for (const [key, field] of Object.entries(extracted)) {
    if (key === "line_items" || key === "periods") continue;
    if (field && typeof field === "object" && !Array.isArray(field)) {
      const missing = field.value === null || field.value === undefined || field.value === "";
      
      let displayValue = field.value;
      if (typeof field.value === "number") {
        displayValue = field.value.toLocaleString(undefined, { maximumFractionDigits: 2 });
      }

      cards.push(`
        <div class="field-card ${missing ? "missing" : ""}">
          <div class="label">${escapeHtml(key.replace(/_/g, " "))}</div>
          <div class="value">${missing ? "— null / missing —" : escapeHtml(displayValue)}</div>
          ${field.page_number ? `<div class="evidence">📍 Page ${escapeHtml(field.page_number)}</div>` : ""}
          ${field.source_text ? `<div class="evidence" style="font-style:italic">"${escapeHtml(field.source_text)}"</div>` : ""}
        </div>
      `);
    }
  }
  container.innerHTML = `<div class="field-grid">${cards.join("")}</div>`;
}

function renderLineItems(extracted) {
  const container = document.getElementById("line-items");
  const items = extracted?.line_items;
  if (!items || items.length === 0) {
    container.innerHTML = `<p class="empty">No line items / table rows detected.</p>`;
    return;
  }
  if (items[0].amount !== undefined) {
    // Invoice Line Items
    container.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Description</th>
            <th>Quantity</th>
            <th>Unit Price</th>
            <th>Total Amount</th>
          </tr>
        </thead>
        <tbody>
          ${items.map(i => `
            <tr>
              <td><strong style="color:var(--text-primary)">${escapeHtml(i.description)}</strong></td>
              <td>${escapeHtml(i.quantity)}</td>
              <td>$${typeof i.unit_price === 'number' ? i.unit_price.toFixed(2) : escapeHtml(i.unit_price)}</td>
              <td><strong style="color:#a5b4fc">$${typeof i.amount === 'number' ? i.amount.toFixed(2) : escapeHtml(i.amount)}</strong></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  } else {
    // Statement Line Items
    const periodSet = new Set();
    items.forEach(i => Object.keys(i.values || {}).forEach(p => periodSet.add(p)));
    const periods = Array.from(periodSet);
    container.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Label</th>
            <th>Section Header</th>
            ${periods.map(p => `<th>${escapeHtml(p)}</th>`).join("")}
          </tr>
        </thead>
        <tbody>
          ${items.map(i => `
            <tr>
              <td><strong style="color:var(--text-primary)">${escapeHtml(i.label)}</strong></td>
              <td><span style="font-size:12px;color:var(--text-muted);background:rgba(30,41,59,0.5);padding:2px 6px;border-radius:4px">${escapeHtml(i.section || "N/A")}</span></td>
              ${periods.map(p => {
                const val = i.values && i.values[p] !== undefined ? i.values[p] : "";
                const fmt = typeof val === 'number' ? val.toLocaleString() : val;
                return `<td><strong>${escapeHtml(fmt)}</strong></td>`;
              }).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }
}

function renderValidation(validation) {
  const container = document.getElementById("validation-results");
  if (!validation || !validation.checks || validation.checks.length === 0) {
    container.innerHTML = `<p class="empty">No financial formula checks applicable for this document.</p>`;
    return;
  }

  const cards = validation.checks.map(c => {
    const isFail = c.status === "FAIL";
    const isPass = c.status === "PASS";
    return `
      <div class="check-card ${isFail ? "fail" : isPass ? "pass" : ""}">
        <div class="check-header">
          <div class="check-title">${escapeHtml(c.name.replace(/_/g, " "))}${c.period ? ` (${escapeHtml(c.period)})` : ""}</div>
          ${statusBadge(c.status)}
        </div>
        <div class="check-formula">Formula: ${escapeHtml(c.formula)}</div>
        <div class="check-metrics">
          <div>Calculated: <strong>${c.calculated_value !== null && c.calculated_value !== undefined ? c.calculated_value.toLocaleString() : '—'}</strong></div>
          <div>Reported: <strong>${c.reported_value !== null && c.reported_value !== undefined ? c.reported_value.toLocaleString() : '—'}</strong></div>
          <div>Variance: <strong style="color:${c.variance !== 0 && c.variance !== null ? '#f43f5e' : 'var(--text-primary)'}">${c.variance !== null && c.variance !== undefined ? c.variance.toLocaleString() : '—'}</strong></div>
        </div>
      </div>
    `;
  });

  container.innerHTML = `
    <div style="margin-bottom:16px;display:flex;align-items:center;gap:12px">
      <span>Reconciliation Summary:</span>
      ${statusBadge(validation.overall_status)}
    </div>
    ${cards.join("")}
  `;
}

async function loadDocument() {
  const name = getDocNameFromUrl();
  try {
    const res = await fetch(`${API_BASE}/documents/${encodeURIComponent(name)}`);
    if (!res.ok) {
      document.getElementById("result-summary").innerHTML = `<p style="color:#f43f5e">Document "${escapeHtml(name)}" not found.</p>`;
      return;
    }
    const data = await res.json();
    renderSummary(data);
    renderFileValidation(data.file_validation);
    renderExtractedFields(data.extracted_data);
    renderLineItems(data.extracted_data);
    renderValidation(data.validation);
    document.getElementById("raw-json").textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    document.getElementById("result-summary").innerHTML = `<p style="color:#f43f5e">Failed to load result: ${escapeHtml(e.message)}</p>`;
  }
}

// JSON Copy & Toggle Button Handlers
document.getElementById("toggle-json-btn").addEventListener("click", () => {
  document.getElementById("raw-json").classList.toggle("hidden");
});

document.getElementById("copy-json-btn").addEventListener("click", () => {
  const jsonText = document.getElementById("raw-json").textContent;
  navigator.clipboard.writeText(jsonText).then(() => {
    const btn = document.getElementById("copy-json-btn");
    btn.textContent = "✅ Copied!";
    setTimeout(() => btn.textContent = "📋 Copy JSON", 2000);
  });
});

loadDocument();
