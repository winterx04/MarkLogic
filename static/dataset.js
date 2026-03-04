// =============================
// === TAB SWITCHING LOGIC ===
// =============================
const tabBtns = document.querySelectorAll(".dataset-tab-btn");
const tabPanels = document.querySelectorAll(".dataset-tab-panel");

tabBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    const tabName = btn.dataset.tab;
    tabBtns.forEach((b) => b.classList.remove("active"));
    tabPanels.forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    const panel = document.getElementById(`${tabName}-panel`);
    if (panel) panel.classList.add("active");
  });
});

// Activate first tab by default (if none active)
if (!document.querySelector(".dataset-tab-btn.active") && tabBtns.length) {
  tabBtns[0].click();
}

// =============================
// === FILE UPLOAD HANDLING ===
// =============================
const uploadArea = document.getElementById("uploadArea");
const fileInput = document.getElementById("fileInput");
const uploadBtn = document.getElementById("uploadBtn");
let selectedFiles = [];

// Create dynamic file list container
const fileListContainer = document.createElement("div");
fileListContainer.classList.add("dataset-file-list");
if (uploadArea) uploadArea.insertAdjacentElement("afterend", fileListContainer);

if (uploadArea) {
  uploadArea.addEventListener("click", () => fileInput.click());
}

if (fileInput) {
  fileInput.addEventListener("change", (e) => addFiles(Array.from(e.target.files)));
}

if (uploadArea) {
  uploadArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadArea.classList.add("dragover");
  });
  uploadArea.addEventListener("dragleave", () => uploadArea.classList.remove("dragover"));
  uploadArea.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadArea.classList.remove("dragover");
    addFiles(Array.from(e.dataTransfer.files));
  });
}

function addFiles(newFiles) {
  if (selectedFiles.length >= 1) {
    showPopup("You can only upload one file at a time.", true);
    return;
  }
  if (newFiles.length > 1) {
    showPopup("Please select only one file.", true);
    return;
  }

  const file = newFiles[0];
  selectedFiles = [file];
  renderFileList();
  updateUploadButton();
}

function renderFileList() {
  fileListContainer.innerHTML = "";
  if (selectedFiles.length === 0) {
    fileListContainer.style.display = "none";
    return;
  }
  fileListContainer.style.display = "block";

  const file = selectedFiles[0];
  const item = document.createElement("div");
  item.classList.add("dataset-file-item");

  const icon = document.createElement("div");
  icon.classList.add("dataset-file-icon");
  icon.innerHTML = getFileIcon(file.type);

  const info = document.createElement("div");
  info.classList.add("dataset-file-info");
  info.innerHTML = `
    <div class="dataset-file-name">${file.name}</div>
    <div class="dataset-file-meta">${formatFileSize(file.size)}</div>
  `;

  const removeBtn = document.createElement("button");
  removeBtn.classList.add("dataset-remove-icon");
  removeBtn.innerHTML = `<img src="file-icons/close.png" alt="Remove" style="width:16px; height:16px; object-fit:contain;">`;
  removeBtn.addEventListener("click", removeFile);

  item.append(icon, info, removeBtn);
  fileListContainer.appendChild(item);
}

function removeFile() {
  selectedFiles = [];
  renderFileList();
  updateUploadButton();
}

function getFileIcon(type) {
  let iconPath = "file-icons/folder.png";
  if (type && type.startsWith && type.startsWith("image/")) iconPath = "file-icons/image.png";
  else if (type && type.includes && type.includes("pdf")) iconPath = "file-icons/pdf.png";
  else if (type && type.includes && type.includes("word")) iconPath = "file-icons/word.png";
  else if (type && type.includes && (type.includes("excel") || type.includes("spreadsheet"))) iconPath = "file-icons/excel.png";
  else if (type && type.includes && (type.includes("presentation") || type.includes("powerpoint"))) iconPath = "file-icons/ppt.png";
  return `<img src="${iconPath}" alt="file icon" class="dataset-file-icon-img">`;
}

function formatFileSize(bytes) {
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024 / 1024).toFixed(1)} MB`;
}

function updateUploadButton() {
  if (!uploadBtn) return;
  if (selectedFiles.length > 0) {
    uploadBtn.disabled = false;
    uploadBtn.textContent = "Upload 1 File";
  } else {
    uploadBtn.disabled = true;
    uploadBtn.textContent = "Upload File";
  }
}

// initialize upload button state
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
  const yearNumber = parseInt(year, 10);

  if (!batchNumber || !year) {
    showPopup("Please enter both batch number and year.", true);
    return false;
  }
  if (!/^\d{1,2}$/.test(batchNumber)) {
    showPopup("Batch number must be 1–2 digits.", true);
    return false;
  }
  if (!/^\d{4}$/.test(year) || yearNumber > currentYear) {
    showPopup(`Year must be a valid 4-digit year not exceeding ${currentYear}.`, true);
    return false;
  }
  return true;
}

// =============================
// === UPLOAD TAB ACTION ===
// =============================
if (uploadBtn) {
  uploadBtn.addEventListener("click", () => {
    const batchNumber = document.getElementById("batchNumber").value.trim();
    const year = document.getElementById("yearInput").value.trim();

    if (!validateBatchAndYear(batchNumber, year)) return;
    if (selectedFiles.length === 0) {
      showPopup("Please select a file before uploading.", true);
      return;
    }

    const formData = new FormData();
    formData.append('file', selectedFiles[0]);
    formData.append('batch_number', batchNumber);
    formData.append('batch_year', year);

    const originalBtnText = uploadBtn.innerText;
    uploadBtn.innerText = "⏳ Processing AI Models...";
    uploadBtn.disabled = true;

    fetch('/upload-journal/MYIPO', {
      method: 'POST',
      body: formData
    })
    .then(async response => {
      let data;
      try {
        data = await response.json();
      } catch {
        throw new Error("Server returned invalid JSON. Check console.");
      }

      if (data.success) {
        showPopup(`✅ ${data.message}`);
        selectedFiles = [];
        renderFileList();
        updateUploadButton();
        document.getElementById("batchNumber").value = "";
        document.getElementById("yearInput").value = "";
        // After successful upload, refresh manage table if present
        if (typeof loadTrademarks === "function") loadTrademarks();
      } else {
        showPopup(`❌ Error: ${data.message}`, true);
      }
    })
    .catch(error => {
      console.error('Upload Error:', error);
      showPopup("❌ A server error occurred. Check the console.", true);
    })
    .finally(() => {
      uploadBtn.innerText = originalBtnText;
      uploadBtn.disabled = false;
    });
  });
}

// =============================
// === MANAGE TAB FUNCTIONALITY (DYNAMIC) ===
// =============================

/**
 * Renders the manage table rows using fetched trademark data.
 * Each item expected: { id, display_name, trademark_name, class_indices, applicant_name, has_logo }
 */
function renderManageTable(trademarks) {
  const tbody = document.getElementById("fileTableBody");
  if (!tbody) return;

  tbody.innerHTML = "";

  if (!trademarks || trademarks.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 2;
    td.style.textAlign = "center";
    td.textContent = "No files found.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  trademarks.forEach(item => {
    const tr = document.createElement("tr");

    const tdCheckbox = document.createElement("td");
    tdCheckbox.classList.add("table-checkbox-col");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.classList.add("manage-checkbox");
    cb.dataset.id = item.id;
    tdCheckbox.appendChild(cb);

    const tdName = document.createElement("td");
    tdName.textContent = item.display_name || item.trademark_name || `id-${item.id}`;

    if (item.has_logo) {
      const logoMark = document.createElement("span");
      logoMark.style.marginLeft = "8px";
      logoMark.title = "Has logo";
      logoMark.textContent = "🖼️";
      tdName.appendChild(logoMark);
    }

    tr.appendChild(tdCheckbox);
    tr.appendChild(tdName);
    tbody.appendChild(tr);
  });

  // Reset selectAll checkbox state
  const selectAllCheckbox = document.getElementById("selectAll");
  const allBoxes = document.querySelectorAll(".manage-checkbox:not(#selectAll)");
  const checkedBoxes = document.querySelectorAll(".manage-checkbox:not(#selectAll):checked");
  if (selectAllCheckbox) selectAllCheckbox.checked = (allBoxes.length === checkedBoxes.length && allBoxes.length > 0);
}

/**
 * Load trademarks from server with optional batch/year filters.
 * Calls GET /api/trademarks?batch_number=...&batch_year=...
 */
async function loadTrademarks({batch=null, year=null, q=null} = {}) {
  const params = new URLSearchParams();
  if (batch) params.append('batch_number', batch);
  if (year) params.append('batch_year', year);
  if (q) params.append('q', q);

  try {
    const res = await fetch('/api/trademarks?' + params.toString());
    if (!res.ok) {
      const text = await res.text();
      console.error('Non-OK response from /api/trademarks:', res.status, text);
      showPopup("Failed to fetch files from server.", true);
      return;
    }
    const payload = await res.json();
    if (payload.success) {
      renderManageTable(payload.trademarks);
    } else {
      showPopup("Error fetching data from server.", true);
    }
  } catch (err) {
    console.error('Fetch error', err);
    showPopup("Server error while fetching files.", true);
  }
}

// Auto-load manage data when the manage panel exists
// if (document.getElementById("fileTableBody")) {
//   // initial load
//   loadTrademarks();
// }

// Keep Select All checkbox logic (works with dynamic rows)
const selectAllCheckbox = document.getElementById("selectAll");
if (selectAllCheckbox) {
  selectAllCheckbox.addEventListener("change", (e) => {
    const checkboxes = document.querySelectorAll(".manage-checkbox:not(#selectAll)");
    checkboxes.forEach((box) => (box.checked = e.target.checked));
  });
}

// Keep Select All in sync on changes to row checkboxes (delegated)
document.addEventListener("change", (e) => {
  if (e.target.classList && e.target.classList.contains("manage-checkbox") && e.target.id !== "selectAll") {
    const allBoxes = document.querySelectorAll(".manage-checkbox:not(#selectAll)");
    const checkedBoxes = document.querySelectorAll(".manage-checkbox:not(#selectAll):checked");
    if (selectAllCheckbox) selectAllCheckbox.checked = (allBoxes.length === checkedBoxes.length && allBoxes.length > 0);
  }
});

// Custom Confirmation Popup (re-used from original; defined here only if not present)
if (typeof showConfirmPopup !== "function") {
  function showConfirmPopup(message, onConfirm) {
    let overlay = document.querySelector(".confirm-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "confirm-overlay";
      overlay.innerHTML = `
        <div class="confirm-box">
          <p class="confirm-message"></p>
          <div class="confirm-buttons">
            <button class="confirm-yes">Yes</button>
            <button class="confirm-no">No</button>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);
    }

    overlay.querySelector(".confirm-message").textContent = message;
    overlay.classList.add("show");

    overlay.querySelector(".confirm-yes").onclick = () => {
      overlay.classList.remove("show");
      onConfirm();
    };
    overlay.querySelector(".confirm-no").onclick = () => overlay.classList.remove("show");
  }
}

// Delete Button -> calls server API then refreshes
const deleteBtn = document.querySelector(".manage-delete-btn");
if (deleteBtn) {
  deleteBtn.addEventListener("click", () => {
    const checked = Array.from(document.querySelectorAll(".manage-checkbox:not(#selectAll):checked"));
    if (checked.length === 0) {
      showPopup("Please select at least one file to delete.", true);
      return;
    }

    showConfirmPopup(`Are you sure you want to delete ${checked.length} file(s)?`, async () => {
      const ids = checked.map(c => parseInt(c.dataset.id, 10)).filter(Boolean);
      if (ids.length === 0) {
        showPopup("No valid IDs selected.", true);
        return;
      }

      try {
        const res = await fetch('/api/trademarks', {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json'
            // Add CSRF header here if your app requires it
          },
          body: JSON.stringify({ ids })
        });
        const payload = await res.json();
        if (payload.success) {
          showPopup(`✅ ${payload.deleted} file(s) deleted.`);
          // refresh table
          loadTrademarks();
          if (selectAllCheckbox) selectAllCheckbox.checked = false;
        } else {
          showPopup("❌ Delete failed: " + (payload.message || "server error"), true);
        }
      } catch (err) {
        console.error('Delete error', err);
        showPopup("❌ Server error while deleting.", true);
      }
    });
  });
}

// Search Button -> call server-side search
const searchBtn = document.querySelector(".manage-search-btn");
if (searchBtn) {
  searchBtn.addEventListener("click", () => {
    const batchNumber = document.getElementById("searchBatchNumber").value.trim();
    const year = document.getElementById("searchYear").value.trim();

    if (!batchNumber && !year) {
      showPopup("Please enter batch number or year to search.", true);
      return;
    }

    loadTrademarks({
      batch: batchNumber || null,
      year: year || null
    });
  });
}

function clearManageTable(message = "Please enter batch number and/or year to search.") {
  const tbody = document.getElementById("fileTableBody");
  if (!tbody) return;

  tbody.innerHTML = "";
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = 2;
  td.style.textAlign = "center";
  td.style.opacity = "0.6";
  td.textContent = message;
  tr.appendChild(td);
  tbody.appendChild(tr);

  const selectAll = document.getElementById("selectAll");
  if (selectAll) selectAll.checked = false;
}
clearManageTable();

// Reset Search Button -> clear inputs and reload
const resetSearchBtn = document.getElementById("resetSearchBtn");
if (resetSearchBtn) {
  resetSearchBtn.addEventListener("click", () => {
    document.getElementById("searchBatchNumber").value = "";
    document.getElementById("searchYear").value = "";
    clearManageTable();
    showPopup("🔄 Search cleared. Table reset.");
  });
}

