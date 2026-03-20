// =============================
// === DESC CELL STYLES ===
// =============================
(function injectDescStyles() {
    if (document.getElementById("dataset-desc-styles")) return;
    const style = document.createElement("style");
    style.id = "dataset-desc-styles";
    style.textContent = `
        .desc-preview,
        .desc-full {
            display: inline;
            font-size: 0.85rem;
            line-height: 1.55;
            color: inherit;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .desc-toggle-btn {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            margin-top: 5px;
            padding: 2px 10px;
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.03em;
            color: #a0c4ff;
            background: rgba(100, 88, 240, 0.18);
            border: 1px solid rgba(100, 88, 240, 0.35);
            border-radius: 20px;
            cursor: pointer;
            transition: background 0.18s, color 0.18s;
            white-space: nowrap;
        }
        .desc-toggle-btn:hover {
            background: rgba(100, 88, 240, 0.38);
            color: #fff;
        }
        .tm-logo-thumb {
            width: 56px;
            height: 56px;
            object-fit: contain;
            border-radius: 6px;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1);
            display: block;
        }
        .tm-no-logo {
            width: 56px;
            height: 56px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.4rem;
            border-radius: 6px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
        }
    `;
    document.head.appendChild(style);
})();

// =============================
// === TAB SWITCHING LOGIC ===
// =============================
const tabBtns   = document.querySelectorAll(".dataset-tab-btn");
const tabPanels = document.querySelectorAll(".dataset-tab-panel");

tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
        const tabName = btn.dataset.tab;
        tabBtns.forEach((b) => b.classList.remove("active"));
        tabPanels.forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        const panel = document.getElementById(`${tabName}-panel`);
        if (panel) panel.classList.add("active");

        if (tabName === "manage") {
            loadTrademarks();
        }
    });
});

if (!document.querySelector(".dataset-tab-btn.active") && tabBtns.length) {
    tabBtns[0].click();
}

// =============================
// === FILE UPLOAD HANDLING ===
// =============================
const uploadArea = document.getElementById("uploadArea");
const fileInput  = document.getElementById("fileInput");
const uploadBtn  = document.getElementById("uploadBtn");
let selectedFiles = [];

const fileListContainer = document.createElement("div");
fileListContainer.classList.add("dataset-file-list");
if (uploadArea) uploadArea.insertAdjacentElement("afterend", fileListContainer);

if (uploadArea) uploadArea.addEventListener("click", () => fileInput.click());
if (fileInput)  fileInput.addEventListener("change", (e) => addFiles(Array.from(e.target.files)));

if (uploadArea) {
    uploadArea.addEventListener("dragover", (e) => { e.preventDefault(); uploadArea.classList.add("dragover"); });
    uploadArea.addEventListener("dragleave", () => uploadArea.classList.remove("dragover"));
    uploadArea.addEventListener("drop", (e) => {
        e.preventDefault();
        uploadArea.classList.remove("dragover");
        addFiles(Array.from(e.dataTransfer.files));
    });
}

function addFiles(newFiles) {
    if (selectedFiles.length >= 1) { showPopup("You can only upload one file at a time.", true); return; }
    if (newFiles.length > 1)       { showPopup("Please select only one file.", true); return; }
    selectedFiles = [newFiles[0]];
    renderFileList();
    updateUploadButton();
}

function renderFileList() {
    fileListContainer.innerHTML = "";
    if (selectedFiles.length === 0) { fileListContainer.style.display = "none"; return; }
    fileListContainer.style.display = "block";

    const file      = selectedFiles[0];
    const item      = document.createElement("div");
    item.classList.add("dataset-file-item");

    const icon = document.createElement("div");
    icon.classList.add("dataset-file-icon");
    icon.innerHTML = getFileIcon(file.type);

    const info = document.createElement("div");
    info.classList.add("dataset-file-info");
    info.innerHTML = `<div class="dataset-file-name">${file.name}</div><div class="dataset-file-meta">${formatFileSize(file.size)}</div>`;

    const removeBtn = document.createElement("button");
    removeBtn.classList.add("dataset-remove-icon");
    removeBtn.innerHTML = `<img src="file-icons/close.png" alt="Remove" style="width:16px;height:16px;object-fit:contain;">`;
    removeBtn.addEventListener("click", removeFile);

    item.append(icon, info, removeBtn);
    fileListContainer.appendChild(item);
}

function removeFile() { selectedFiles = []; renderFileList(); updateUploadButton(); }

function getFileIcon(type) {
    let p = "file-icons/folder.png";
    if (type?.startsWith("image/"))                                        p = "file-icons/image.png";
    else if (type?.includes("pdf"))                                        p = "file-icons/pdf.png";
    else if (type?.includes("word"))                                       p = "file-icons/word.png";
    else if (type?.includes("excel") || type?.includes("spreadsheet"))    p = "file-icons/excel.png";
    else if (type?.includes("presentation") || type?.includes("powerpoint")) p = "file-icons/ppt.png";
    return `<img src="${p}" alt="file icon" class="dataset-file-icon-img">`;
}

function formatFileSize(bytes) {
    const kb = bytes / 1024;
    return kb < 1024 ? `${kb.toFixed(1)} KB` : `${(kb / 1024).toFixed(1)} MB`;
}

function updateUploadButton() {
    if (!uploadBtn) return;
    uploadBtn.disabled    = selectedFiles.length === 0;
    uploadBtn.textContent = selectedFiles.length > 0 ? "Upload 1 File" : "Upload File";
}
updateUploadButton();

// =============================
// === POPUP NOTIFICATION ===
// =============================
function showPopup(message, isError = false) {
    let popup = document.querySelector(".upload-popup");
    if (!popup) {
        popup = document.createElement("div");
        popup.className = "upload-popup";
        document.body.appendChild(popup);
    }
    popup.textContent = message;
    popup.classList.add("show");
    popup.classList.toggle("error", isError);
    setTimeout(() => popup.classList.remove("show"), 3000);
}

// =============================
// === VALIDATION ===
// =============================
function validateBatchAndYear(batchNumber, year) {
    const currentYear = new Date().getFullYear();
    if (!batchNumber || !year)                                          { showPopup("Please enter both batch number and year.", true); return false; }
    if (!/^\d{1,2}$/.test(batchNumber))                                { showPopup("Batch number must be 1–2 digits.", true); return false; }
    if (!/^\d{4}$/.test(year) || parseInt(year, 10) > currentYear)    { showPopup(`Year must be a valid 4-digit year not exceeding ${currentYear}.`, true); return false; }
    return true;
}

// =============================
// === UPLOAD TAB ACTION ===
// =============================
if (uploadBtn) {
    uploadBtn.addEventListener("click", async () => {
        const batchNumber = document.getElementById("batchNumber").value.trim();
        const year        = document.getElementById("yearInput").value.trim();

        if (!validateBatchAndYear(batchNumber, year)) return;
        if (selectedFiles.length === 0) { showPopup("Please select a file before uploading.", true); return; }

        const progressContainer = document.getElementById("progressContainer");
        const progressBar       = document.getElementById("progressBar");
        const progressPercent   = document.getElementById("progressPercent");
        const progressText      = document.getElementById("progressText");

        const formData = new FormData();
        formData.append("file",         selectedFiles[0]);
        formData.append("batch_number", batchNumber);
        formData.append("batch_year",   year);

        const originalBtnText = uploadBtn.innerText;
        uploadBtn.innerText   = "⏳ Initializing AI...";
        uploadBtn.disabled    = true;
        progressContainer.style.display   = "block";
        progressBar.style.width           = "0%";
        progressBar.style.backgroundColor = "#4cc9f0";
        progressPercent.innerText         = "0%";

        try {
            const response = await fetch("/upload-journal/MYIPO", { method: "POST", body: formData });
            if (!response.ok) throw new Error("Server error");

            const reader  = response.body.getReader();
            const decoder = new TextDecoder();
            let leftover  = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                const combined = leftover + decoder.decode(value, { stream: true });
                const lines    = combined.split("\n");
                leftover       = lines.pop();

                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const data = JSON.parse(line);
                        if (data.status === "extracting") {
                            progressBar.style.width   = `${data.percentage}%`;
                            progressPercent.innerText = `${data.percentage}%`;
                            progressText.innerText    = `AI reading PDF: Page ${data.current_page}`;
                            uploadBtn.innerText       = `⏳ Extracting... ${data.percentage}%`;
                        } else if (data.status === "inserting") {
                            progressBar.style.backgroundColor = "#2ecc71";
                            progressBar.style.width   = `${data.percentage}%`;
                            progressPercent.innerText = `${data.percentage}%`;
                            progressText.innerText    = `Saving to DB: ${data.current} of ${data.total}`;
                            uploadBtn.innerText       = `💾 Saving... ${data.percentage}%`;
                        } else if (data.status === "complete") {
                            showPopup(`✅ ${data.message}`);
                            selectedFiles = [];
                            renderFileList();
                            document.getElementById("batchNumber").value = "";
                            document.getElementById("yearInput").value   = "";
                        } else if (data.status === "error") {
                            showPopup(`❌ Error: ${data.message}`, true);
                        }
                    } catch (e) { console.warn("Stream parse error:", e); }
                }
            }
        } catch (error) {
            console.error("Upload Error:", error);
            showPopup("❌ Server error. Check console.", true);
        } finally {
            uploadBtn.innerText = originalBtnText;
            uploadBtn.disabled  = false;
            setTimeout(() => { progressContainer.style.display = "none"; }, 5000);
        }
    });
}

// =============================
// === MANAGE TAB — DESC CELL ===
// =============================
const DESC_LIMIT = 120;

function makeDescCell(description) {
    const text = description || "N/A";
    const td   = document.createElement("td");

    if (text.length <= DESC_LIMIT) {
        td.textContent = text;
        return td;
    }

    td.style.cssText = "max-width:300px; vertical-align:top;";

    const preview       = document.createElement("span");
    preview.className   = "desc-preview";
    preview.textContent = text.slice(0, DESC_LIMIT) + "…";

    const full           = document.createElement("span");
    full.className       = "desc-full";
    full.textContent     = text;
    full.style.display   = "none";

    const toggle     = document.createElement("button");
    toggle.className = "desc-toggle-btn";
    toggle.innerHTML = "&#9660; Show more";

    toggle.addEventListener("click", e => {
        e.stopPropagation();
        const expanded        = full.style.display !== "none";
        preview.style.display = expanded ? "inline" : "none";
        full.style.display    = expanded ? "none"   : "inline";
        toggle.innerHTML      = expanded ? "&#9660; Show more" : "&#9650; Show less";
    });

    td.appendChild(preview);
    td.appendChild(full);
    td.appendChild(document.createElement("br"));
    td.appendChild(toggle);
    return td;
}

// =============================
// === MANAGE TAB — RENDER ===
// =============================
function renderManageTable(trademarks) {
    const tbody = document.getElementById("fileTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!trademarks || trademarks.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:20px;opacity:0.6;">No records found.</td></tr>`;
        return;
    }

    trademarks.forEach(item => {
        const tr = document.createElement("tr");

        // Checkbox
        const tdCheck     = document.createElement("td");
        tdCheck.className = "table-checkbox-col";
        const cb          = document.createElement("input");
        cb.type           = "checkbox";
        cb.className      = "manage-checkbox";
        cb.dataset.id     = item.id;
        tdCheck.appendChild(cb);

        // Logo
        const tdLogo           = document.createElement("td");
        tdLogo.style.textAlign = "center";
        if (item.has_logo) {
            const img     = document.createElement("img");
            img.src       = `/logo/${item.id}`;
            img.className = "tm-logo-thumb";
            img.alt       = "logo";
            tdLogo.appendChild(img);
        } else {
            const ph           = document.createElement("div");
            ph.className       = "tm-no-logo";
            ph.textContent     = "—";
            tdLogo.appendChild(ph);
        }

        // Applicant
        const tdApplicant       = document.createElement("td");
        tdApplicant.textContent = item.applicant_name || "N/A";

        // Class
        const tdClass            = document.createElement("td");
        tdClass.textContent      = item.class_indices || "N/A";
        tdClass.style.whiteSpace = "nowrap";

        // Description (collapsible)
        const tdDesc = makeDescCell(item.description);

        // Batch / Year
        const tdBatch            = document.createElement("td");
        tdBatch.textContent      = (item.batch_number && item.batch_year)
            ? `${item.batch_number} / ${item.batch_year}`
            : item.display_name || "N/A";
        tdBatch.style.whiteSpace = "nowrap";

        // 6 columns: checkbox, logo, applicant, class, description, batch/year
        tr.append(tdCheck, tdLogo, tdApplicant, tdClass, tdDesc, tdBatch);
        tbody.appendChild(tr);
    });

    // Sync selectAll
    const selectAll = document.getElementById("selectAll");
    const allBoxes  = document.querySelectorAll(".manage-checkbox:not(#selectAll)");
    const checked   = document.querySelectorAll(".manage-checkbox:not(#selectAll):checked");
    if (selectAll) selectAll.checked = allBoxes.length > 0 && allBoxes.length === checked.length;
}

// =============================
// === MANAGE TAB — LOAD ===
// =============================
async function loadTrademarks({ batch = null, year = null } = {}) {
    const tbody = document.getElementById("fileTableBody");
    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:20px;">Loading…</td></tr>`;
    }

    const params = new URLSearchParams();
    if (batch) params.append("batch_number", batch);
    if (year)  params.append("batch_year",   year);

    try {
        const res = await fetch("/api/trademarks?" + params.toString());
        if (!res.ok) { showPopup("Failed to fetch records from server.", true); return; }
        const payload = await res.json();
        if (payload.success) {
            renderManageTable(payload.trademarks);
        } else {
            showPopup("Error fetching data from server.", true);
        }
    } catch (err) {
        console.error("Fetch error:", err);
        showPopup("Server error while fetching records.", true);
    }
}

// =============================
// === SELECT ALL CHECKBOX ===
// =============================
const selectAllCheckbox = document.getElementById("selectAll");
if (selectAllCheckbox) {
    selectAllCheckbox.addEventListener("change", (e) => {
        document.querySelectorAll(".manage-checkbox:not(#selectAll)")
            .forEach(cb => { cb.checked = e.target.checked; });
    });
}

document.addEventListener("change", (e) => {
    if (e.target.classList.contains("manage-checkbox") && e.target.id !== "selectAll") {
        const all     = document.querySelectorAll(".manage-checkbox:not(#selectAll)");
        const checked = document.querySelectorAll(".manage-checkbox:not(#selectAll):checked");
        if (selectAllCheckbox) selectAllCheckbox.checked = all.length > 0 && all.length === checked.length;
    }
});

// =============================
// === SEARCH BUTTON ===
// =============================
const searchBtn = document.getElementById("btnSearchDataset");
if (searchBtn) {
    searchBtn.addEventListener("click", () => {
        const batchNumber = document.getElementById("searchBatchNumber").value.trim();
        const yearInput   = document.getElementById("searchYear").value.trim();

        if (yearInput) {
            const currentYear = new Date().getFullYear();
            if (!/^\d{4}$/.test(yearInput)) { showPopup("Year must be a 4-digit number (e.g., 2024).", true); return; }
            if (parseInt(yearInput, 10) > currentYear) { showPopup(`Year cannot exceed the current year (${currentYear}).`, true); return; }
        }
        if (batchNumber && !/^\d{1,2}$/.test(batchNumber)) { showPopup("Batch number must be 1–2 digits.", true); return; }

        loadTrademarks({ batch: batchNumber || null, year: yearInput || null });
    });
}

// =============================
// === RESET BUTTON ===
// =============================
const resetSearchBtn = document.getElementById("resetSearchBtn");
if (resetSearchBtn) {
    resetSearchBtn.addEventListener("click", () => {
        document.getElementById("searchBatchNumber").value = "";
        document.getElementById("searchYear").value        = "";
        loadTrademarks();
        showPopup("🔄 Search cleared.");
    });
}

// =============================
// === DELETE BUTTON ===
// =============================
const deleteBtn = document.getElementById("deleteDatasetBtn");
if (deleteBtn) {
    deleteBtn.addEventListener("click", () => {
        const checked = Array.from(document.querySelectorAll(".manage-checkbox:not(#selectAll):checked"));
        if (checked.length === 0) { showPopup("Please select at least one record to delete.", true); return; }
        if (!confirm(`Delete ${checked.length} record(s)? This cannot be undone.`)) return;

        const ids = checked.map(c => parseInt(c.dataset.id, 10)).filter(Boolean);
        fetch("/api/trademarks", {
            method:  "DELETE",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ ids })
        })
        .then(r => r.json())
        .then(payload => {
            if (payload.success) {
                showPopup(`✅ ${payload.deleted} record(s) deleted.`);
                loadTrademarks();
                if (selectAllCheckbox) selectAllCheckbox.checked = false;
            } else {
                showPopup("❌ Delete failed: " + (payload.message || "server error"), true);
            }
        })
        .catch(err => { console.error("Delete error:", err); showPopup("❌ Server error while deleting.", true); });
    });
}