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
    document.getElementById(`${tabName}-panel`).classList.add("active");
  });
});

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
uploadArea.insertAdjacentElement("afterend", fileListContainer);

uploadArea.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (e) => addFiles(Array.from(e.target.files)));

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
  if (type.startsWith("image/")) iconPath = "file-icons/image.png";
  else if (type.includes("pdf")) iconPath = "file-icons/pdf.png";
  else if (type.includes("word")) iconPath = "file-icons/word.png";
  else if (type.includes("excel") || type.includes("spreadsheet")) iconPath = "file-icons/excel.png";
  else if (type.includes("presentation") || type.includes("powerpoint")) iconPath = "file-icons/ppt.png";
  return `<img src="${iconPath}" alt="file icon" class="dataset-file-icon-img">`;
}

function formatFileSize(bytes) {
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function updateUploadButton() {
  if (selectedFiles.length > 0) {
    uploadBtn.disabled = false;
    uploadBtn.textContent = "Upload 1 File";
  } else {
    uploadBtn.disabled = true;
    uploadBtn.textContent = "Upload File";
  }
}

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
// === UPLOAD TAB ACTION ===
// =============================
// =============================
// === UPLOAD TAB ACTION ===
// =============================
uploadBtn.addEventListener("click", () => {
  const fileNameInput = document.getElementById("fileName");
  const fileName = fileNameInput.value.trim();

  if (selectedFiles.length === 0) {
    showPopup("Please select a file before uploading.", true);
    return;
  }

  const originalFile = selectedFiles[0];
  const originalName = originalFile.name;
  const extension = originalName.substring(originalName.lastIndexOf("."));
  const baseOriginalName = originalName.substring(0, originalName.lastIndexOf("."));

  // If no new name entered → use the same file name directly
  if (!fileName) {
    showPopup(`✅ File "${originalName}" uploaded successfully!`);
    resetUploadUI();
    return;
  }

  // If new name entered → confirm rename
  if (fileName !== baseOriginalName) {
    showConfirmPopup(
      `Are you sure you want to rename "${baseOriginalName}${extension}" to "${fileName}${extension}" before uploading?`,
      () => {
        showPopup(`✅ File name changed to "${fileName}${extension}" and uploaded successfully!`);
        resetUploadUI();
      }
    );
  } else {
    showPopup(`✅ File "${originalName}" uploaded successfully!`);
    resetUploadUI();
  }
});

// Helper function to clear UI after upload
function resetUploadUI() {
  selectedFiles = [];
  renderFileList();
  updateUploadButton();
  document.getElementById("fileName").value = "";
}

// =============================
// === MANAGE TAB FUNCTIONALITY ===
// =============================

// Select All Checkbox
const selectAllCheckbox = document.getElementById("selectAll");
if (selectAllCheckbox) {
  selectAllCheckbox.addEventListener("change", (e) => {
    const checkboxes = document.querySelectorAll(".manage-checkbox:not(#selectAll)");
    checkboxes.forEach((box) => (box.checked = e.target.checked));
  });
}

// Keep Select All in sync
document.addEventListener("change", (e) => {
  if (e.target.classList.contains("manage-checkbox") && e.target.id !== "selectAll") {
    const allBoxes = document.querySelectorAll(".manage-checkbox:not(#selectAll)");
    const checkedBoxes = document.querySelectorAll(".manage-checkbox:not(#selectAll):checked");
    if (selectAllCheckbox) selectAllCheckbox.checked = allBoxes.length === checkedBoxes.length;
  }
});

// Custom Confirmation Popup
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

// Delete Button
const deleteBtn = document.querySelector(".manage-delete-btn");
if (deleteBtn) {
  deleteBtn.addEventListener("click", () => {
    const checked = document.querySelectorAll(".manage-checkbox:not(#selectAll):checked");
    if (checked.length === 0) {
      showPopup("Please select at least one file to delete.", true);
      return;
    }

    showConfirmPopup(`Are you sure you want to delete ${checked.length} file(s)?`, () => {
      checked.forEach((c) => c.closest("tr").remove());
      showPopup(`✅ ${checked.length} file(s) deleted successfully!`);
      if (selectAllCheckbox) selectAllCheckbox.checked = false;
    });
  });
}

// Search Button
const searchBtn = document.querySelector(".manage-search-btn");
if (searchBtn) {
  searchBtn.addEventListener("click", () => {
    const searchTerm = document.getElementById("searchFileName").value.trim();

    if (!searchTerm) {
      showPopup("Please enter a file name to search.", true);
      return;
    }

    showPopup(`🔍 Searching for "${searchTerm}"...`);
    // (Future: Filter table results here)
  });
}