/**
 * client-dataset.js
 * Upload tab: accepts image OR PDF (multi-trademark)
 * Progress: two-phase — extraction (0-50%) then saving (50-100%)
 */

document.addEventListener('DOMContentLoaded', () => {

// ── Inject description-cell styles (no stylesheet edit required) ─────────────
(function injectDescStyles() {
    if (document.getElementById("desc-cell-styles")) return;
    const style = document.createElement("style");
    style.id = "desc-cell-styles";
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
    `;
    document.head.appendChild(style);
})();


    // ── Selectors ────────────────────────────────────────────────────────────
    const tabBtns   = document.querySelectorAll(".dataset-tab-btn");
    const tabPanels = document.querySelectorAll(".dataset-tab-panel");

    const uploadArea        = document.getElementById("uploadArea");
    const fileInput         = document.getElementById("fileInput");
    const uploadBtn         = document.getElementById("uploadBtn");

    const progressContainer = document.getElementById("progressContainer");
    const progressBar       = document.getElementById("progressBar");
    const progressPercent   = document.getElementById("progressPercent");
    const progressText      = document.getElementById("progressText");
    const progressPhase     = document.getElementById("progressPhase");
    const progressCounter   = document.getElementById("progressCounter");

    const uploadIdleState   = document.getElementById("uploadIdleState");
    const uploadPreviewState= document.getElementById("uploadPreviewState");
    const imagePreviewWrap  = document.getElementById("imagePreviewWrap");
    const pdfPreviewWrap    = document.getElementById("pdfPreviewWrap");
    const imagePreview      = document.getElementById("imagePreview");
    const previewFileName   = document.getElementById("previewFileName");
    const previewFileType   = document.getElementById("previewFileType");

    const tbody      = document.getElementById("clientTableBody");
    const searchInput= document.getElementById("searchClientName");
    const resetBtn   = document.getElementById("resetClientSearch");

    let selectedFile = null;
    let isPDF        = false;

    // ── Tab switching ─────────────────────────────────────────────────────────
    tabBtns.forEach(btn => {
        btn.addEventListener("click", e => {
            e.preventDefault();
            const tab = btn.dataset.tab;
            tabBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            tabPanels.forEach(p => {
                const isTarget = p.id === `${tab}-panel`;
                p.classList.toggle("active", isTarget);
                p.style.display = isTarget ? "block" : "none";
            });
            if (tab === "manage") {
                loadClientTable("");
                setTimeout(attachSearchListener, 100);
            }
        });
    });

    // ── Drag & drop ───────────────────────────────────────────────────────────
    if (uploadArea) {
        uploadArea.addEventListener("click", e => {
            // Don't trigger when clicking the Remove button
            if (e.target.closest("button")) return;
            fileInput.click();
        });
        uploadArea.addEventListener("dragover", e => {
            e.preventDefault();
            uploadArea.classList.add("dragover");
        });
        uploadArea.addEventListener("dragleave", () => uploadArea.classList.remove("dragover"));
        uploadArea.addEventListener("drop", e => {
            e.preventDefault();
            uploadArea.classList.remove("dragover");
            if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
        });
    }

    if (fileInput) {
        fileInput.addEventListener("change", e => {
            if (e.target.files.length > 0) handleFile(e.target.files[0]);
            e.target.value = "";
        });
    }

    // ── File selection handler ────────────────────────────────────────────────
    function handleFile(file) {
        selectedFile = file;
        isPDF        = file.name.toLowerCase().endsWith(".pdf");

        // Show preview
        uploadIdleState.style.display    = "none";
        uploadPreviewState.style.display = "block";
        previewFileName.textContent      = file.name;
        previewFileType.textContent      = isPDF
            ? `📋 PDF — all trademark records inside will be extracted`
            : `🖼️ Image — logo will be extracted and embedded`;

        if (isPDF) {
            imagePreviewWrap.style.display = "none";
            pdfPreviewWrap.style.display   = "block";
        } else {
            pdfPreviewWrap.style.display   = "none";
            imagePreviewWrap.style.display = "block";
            const reader = new FileReader();
            reader.onload = ev => { imagePreview.src = ev.target.result; };
            reader.readAsDataURL(file);
        }

        uploadBtn.disabled = false;
        uploadBtn.innerText = isPDF
            ? "Upload PDF to Client Dataset"
            : "Upload Image to Client Dataset";
    }

    // ── Remove selection ──────────────────────────────────────────────────────
    window.clearFileSelection = function(e) {
        if (e) e.stopPropagation();
        selectedFile = null;
        isPDF        = false;
        uploadIdleState.style.display    = "block";
        uploadPreviewState.style.display = "none";
        imagePreview.src                 = "";
        uploadBtn.disabled               = true;
        uploadBtn.innerText              = "Upload to Client Dataset";
    };

    // ── Progress helpers ──────────────────────────────────────────────────────
    function setProgress(phase, text, pct, counter) {
        progressPhase.textContent   = phase;
        progressText.textContent    = text;
        progressPercent.textContent = `${pct}%`;
        progressBar.style.width     = `${pct}%`;
        if (counter !== undefined) {
            progressCounter.style.display = "block";
            progressCounter.textContent   = counter;
        } else {
            progressCounter.style.display = "none";
        }
    }

    // ── Upload action ─────────────────────────────────────────────────────────
    uploadBtn.addEventListener("click", async () => {
        const fileName = document.getElementById("fileName").value.trim();
        const fileDate = document.getElementById("fileDate").value;

        if (!selectedFile || !fileDate) {
            return showPopup("Please select a file and a date.", true);
        }

        const formData = new FormData();
        formData.append("file",           selectedFile);
        formData.append("user_file_name", fileName || selectedFile.name);
        formData.append("user_date",      fileDate);

        progressContainer.style.display = "block";
        progressCounter.style.display   = "none";
        uploadBtn.disabled  = true;

        if (isPDF) {
            setProgress("Phase 1 of 2 — Extracting", "Starting AI extraction…", 0);
        } else {
            setProgress("Processing image", "Extracting logo…", 0);
        }

        try {
            const response = await fetch("/upload-client-dataset", {
                method: "POST",
                body: formData
            });

            const reader  = response.body.getReader();
            const decoder = new TextDecoder();
            let leftover  = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const lines = (leftover + decoder.decode(value, { stream: true })).split("\n");
                leftover = lines.pop();

                for (const line of lines) {
                    if (!line.trim()) continue;
                    let data;
                    try { data = JSON.parse(line); } catch { continue; }

                    if (data.status === "extracting") {
                        // Phase 1: 0 → 50% of total bar
                        const pct = Math.round((data.percentage || 0) * 0.5);
                        setProgress(
                            "Phase 1 of 2 — Extracting",
                            `AI scanning page ${data.current_page || ""}…`,
                            pct
                        );

                    } else if (data.status === "inserting") {
                        // Phase 2: 50 → 100% of total bar
                        const pct = 50 + Math.round((data.percentage || 0) * 0.5);
                        const counter = data.current && data.total
                            ? `Saved ${data.current} of ${data.total} records`
                            : undefined;
                        setProgress(
                            "Phase 2 of 2 — Saving",
                            `Generating embeddings & saving…`,
                            pct,
                            counter
                        );

                    } else if (data.status === "complete") {
                        setProgress(
                            isPDF ? "Phase 2 of 2 — Done" : "Done",
                            data.message || "Upload complete!",
                            100
                        );
                        showPopup("✅ " + (data.message || "Upload complete!"));
                        setTimeout(() => location.reload(), 2200);

                    } else if (data.status === "error") {
                        showPopup("❌ " + data.message, true);
                        progressContainer.style.display = "none";
                        uploadBtn.disabled = false;
                    }
                }
            }
        } catch (err) {
            console.error(err);
            showPopup("❌ Upload failed: " + err.message, true);
            progressContainer.style.display = "none";
            uploadBtn.disabled = false;
        }
    });

    // ── Manage tab ────────────────────────────────────────────────────────────
    // ── Description cell character limit ────────────────────────────────────
    const DESC_LIMIT = 120; // characters shown before truncation

    function makeDescCell(description) {
        const text = description || "N/A";
        const td   = document.createElement("td");

        if (text.length <= DESC_LIMIT) {
            td.textContent = text;
            return td;
        }

        // Build collapsible cell
        td.style.cssText = "max-width:340px; vertical-align:top;";

        const preview = document.createElement("span");
        preview.className   = "desc-preview";
        preview.textContent = text.slice(0, DESC_LIMIT) + "…";

        const full = document.createElement("span");
        full.className   = "desc-full";
        full.textContent = text;
        full.style.display = "none";

        const toggle = document.createElement("button");
        toggle.className = "desc-toggle-btn";
        toggle.innerHTML = "&#9660; Show more";   // ▼
        toggle.title     = "Expand description";

        toggle.addEventListener("click", e => {
            e.stopPropagation();
            const expanded = full.style.display !== "none";
            preview.style.display = expanded ? "inline" : "none";
            full.style.display    = expanded ? "none"   : "inline";
            toggle.innerHTML      = expanded
                ? "&#9660; Show more"     // ▼
                : "&#9650; Show less";    // ▲
            toggle.title = expanded ? "Expand description" : "Collapse description";
        });

        td.appendChild(preview);
        td.appendChild(full);
        td.appendChild(document.createElement("br"));
        td.appendChild(toggle);
        return td;
    }

    async function loadClientTable(query = "") {
        if (!tbody) return;
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:20px;">Loading…</td></tr>`;
        try {
            const res  = await fetch(`/api/client-trademarks?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            tbody.innerHTML = "";
            if (data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:20px;">No records found.</td></tr>`;
                return;
            }
            data.forEach(item => {
                const row = document.createElement("tr");

                const checkTd = document.createElement("td");
                checkTd.className = "table-checkbox-col";
                checkTd.innerHTML = `<input type="checkbox" class="manage-checkbox" data-id="${item.id}">`;

                const nameTd = document.createElement("td");
                nameTd.textContent = item.applicant_name || "N/A";

                const descTd = makeDescCell(item.description);

                const dateTd = document.createElement("td");
                dateTd.textContent = item.upload_date || "N/A";

                row.appendChild(checkTd);
                row.appendChild(nameTd);
                row.appendChild(descTd);
                row.appendChild(dateTd);
                tbody.appendChild(row);
            });
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="4" style="color:red;text-align:center;">Error loading results.</td></tr>`;
        }
    }

    function attachSearchListener() {
        const btn = document.getElementById("btnSearchClient");
        if (!btn) return;
        const fresh = btn.cloneNode(true);
        btn.parentNode.replaceChild(fresh, btn);
        fresh.addEventListener("click", () => {
            loadClientTable(document.getElementById("searchClientName").value.trim());
        });
    }

    // Delete selected
    const deleteBtn = document.getElementById("deleteClientBtn");
    if (deleteBtn) {
        deleteBtn.addEventListener("click", async () => {
            const checked = [...document.querySelectorAll(".manage-checkbox:checked")];
            if (!checked.length) return showPopup("No records selected.", true);
            const ids = checked.map(cb => parseInt(cb.dataset.id));
            if (!confirm(`Delete ${ids.length} record(s)?`)) return;
            try {
                const res = await fetch("/api/client-trademarks", {
                    method:  "DELETE",
                    headers: { "Content-Type": "application/json" },
                    body:    JSON.stringify({ ids })
                });
                const data = await res.json();
                showPopup(`✅ Deleted ${data.deleted} record(s).`);
                loadClientTable("");
            } catch (e) {
                showPopup("❌ Delete failed.", true);
            }
        });
    }

    // Select all checkbox
    const selectAll = document.getElementById("selectAll");
    if (selectAll) {
        selectAll.addEventListener("change", () => {
            document.querySelectorAll(".manage-checkbox")
                .forEach(cb => { cb.checked = selectAll.checked; });
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener("click", () => {
            if (searchInput) searchInput.value = "";
            loadClientTable("");
            showPopup("Search cleared.");
        });
    }

    // ── Popup helper ──────────────────────────────────────────────────────────
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
        setTimeout(() => popup.classList.remove("show"), 3500);
    }

    attachSearchListener();
});