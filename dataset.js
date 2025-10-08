// === TAB SWITCHING ===
const tabBtns = document.querySelectorAll(".dataset-tab-btn");
const tabPanels = document.querySelectorAll(".dataset-tab-panel");

tabBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    const tabName = btn.dataset.tab;

    // Reset active states
    tabBtns.forEach((b) => b.classList.remove("active"));
    tabPanels.forEach((p) => p.classList.remove("active"));

    // Activate selected
    btn.classList.add("active");
    document.getElementById(`${tabName}-panel`).classList.add("active");
  });
});

// === FILE UPLOAD HANDLING ===
const uploadArea = document.getElementById("uploadArea");
const fileInput = document.getElementById("fileInput");
const uploadBtn = document.getElementById("uploadBtn");

let selectedFiles = [];

// Create file list container
const fileListContainer = document.createElement("div");
fileListContainer.classList.add("dataset-file-list");
uploadArea.insertAdjacentElement("afterend", fileListContainer);

// --- Handle click to browse ---
uploadArea.addEventListener("click", () => fileInput.click());

// --- Handle file selection ---
fileInput.addEventListener("change", (e) => {
  addFiles(Array.from(e.target.files));
});

// --- Handle drag & drop ---
uploadArea.addEventListener("dragover", (e) => {
  e.preventDefault();
  uploadArea.classList.add("dragover");
});

uploadArea.addEventListener("dragleave", () => {
  uploadArea.classList.remove("dragover");
});

uploadArea.addEventListener("drop", (e) => {
  e.preventDefault();
  uploadArea.classList.remove("dragover");
  addFiles(Array.from(e.dataTransfer.files));
});

// === Add files to list ===
function addFiles(newFiles) {
  // Merge unique files by name and size
  newFiles.forEach((file) => {
    if (!selectedFiles.some((f) => f.name === file.name && f.size === file.size)) {
      selectedFiles.push(file);
    }
  });
  renderFileList();
  updateUploadButton();
}

// === Render file preview list ===
function renderFileList() {
  fileListContainer.innerHTML = "";

  if (selectedFiles.length === 0) {
    fileListContainer.style.display = "none";
    return;
  }

  fileListContainer.style.display = "block";

  selectedFiles.forEach((file, index) => {
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
    removeBtn.innerHTML = `<img src="file-icons/close.png" alt="Remove" class="dataset-remove-icon">`;
    removeBtn.addEventListener("click", () => removeFile(index));

    item.appendChild(icon);
    item.appendChild(info);
    item.appendChild(removeBtn);
    fileListContainer.appendChild(item);
  });
}

// === Remove a file ===
function removeFile(index) {
  selectedFiles.splice(index, 1);
  renderFileList();
  updateUploadButton();
}

// === Get file icon based on MIME type ===
// === Get file icon based on MIME type ===
function getFileIcon(type) {
  let iconPath = "file-icons/folder.png"; // default icon

  if (type.startsWith("image/")) {
    iconPath = "file-icons/image.png";
  } else if (type.includes("pdf")) {
    iconPath = "file-icons/pdf.png";
  } else if (type.includes("word")) {
    iconPath = "file-icons/word.png";
  } else if (type.includes("excel") || type.includes("spreadsheet")) {
    iconPath = "file-icons/excel.png";
  } else if (type.includes("presentation") || type.includes("powerpoint")) {
    iconPath = "file-icons/ppt.png";
  }

  return `<img src="${iconPath}" alt="file icon" class="dataset-file-icon-img">`;
}


// === Format file size ===
function formatFileSize(bytes) {
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

// === Update upload button text/state ===
function updateUploadButton() {
  if (selectedFiles.length > 0) {
    uploadBtn.disabled = false;
    uploadBtn.textContent = `Upload ${selectedFiles.length} File${selectedFiles.length > 1 ? "s" : ""}`;
  } else {
    uploadBtn.disabled = true;
    uploadBtn.textContent = "Upload Files";
  }
}

// === Upload Button Click ===
uploadBtn.addEventListener("click", () => {
  if (selectedFiles.length === 0) return;

  alert(`Uploading ${selectedFiles.length} file(s)...`);
  // TODO: Replace this with your actual upload logic (e.g., fetch or FormData)
});
