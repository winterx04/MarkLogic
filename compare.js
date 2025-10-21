const uploadCheckbox = document.getElementById("uploadCheckbox");
const clientDatasetCheckbox = document.getElementById("clientDatasetCheckbox");
const miyoCheckbox = document.getElementById("miyoCheckbox");
const clientDatasetRightCheckbox = document.getElementById("clientDatasetRightCheckbox");
const compareBtn = document.getElementById("compareBtn");
const uploadItem = document.getElementById("uploadItem");
const fileInputUpload = document.getElementById("fileInputUpload");

function updateButtonState() {
  const leftSelected = uploadCheckbox.checked || clientDatasetCheckbox.checked;
  const rightSelected = miyoCheckbox.checked || clientDatasetRightCheckbox.checked;
  compareBtn.disabled = !(leftSelected && rightSelected);
}

function updateVisualState() {
  const items = [
    [uploadCheckbox, uploadItem],
    [clientDatasetCheckbox, document.getElementById("clientDatasetLeft")],
    [miyoCheckbox, document.getElementById("miyoItem")],
    [clientDatasetRightCheckbox, document.getElementById("clientDatasetRight")],
  ];
  items.forEach(([cb, el]) => {
    cb.checked ? el.classList.add("selected") : el.classList.remove("selected");
  });
}

function toggleSelection(clicked, group) {
  if (clicked.checked) {
    group.forEach(cb => {
      if (cb !== clicked) cb.checked = false;
    });
  }
  updateVisualState();
  updateButtonState();
}

[uploadCheckbox, clientDatasetCheckbox].forEach(cb => {
  cb.addEventListener("change", () => toggleSelection(cb, [uploadCheckbox, clientDatasetCheckbox]));
});

[miyoCheckbox, clientDatasetRightCheckbox].forEach(cb => {
  cb.addEventListener("change", () => toggleSelection(cb, [miyoCheckbox, clientDatasetRightCheckbox]));
});

document.getElementById("clientDatasetLeft").addEventListener("click", e => {
  if (!e.target.closest(".compare-page-checkbox")) {
    clientDatasetCheckbox.checked = !clientDatasetCheckbox.checked;
    toggleSelection(clientDatasetCheckbox, [uploadCheckbox, clientDatasetCheckbox]);
  }
});

uploadItem.addEventListener("click", e => {
  if (!e.target.closest(".compare-page-checkbox") && !e.target.closest(".uploaded-files-list")) {
    fileInputUpload.click();
  } else if (e.target.closest(".compare-page-checkbox")) {
    uploadCheckbox.checked = !uploadCheckbox.checked;
    toggleSelection(uploadCheckbox, [uploadCheckbox, clientDatasetCheckbox]);
  }
});

document.getElementById("miyoItem").addEventListener("click", e => {
  if (!e.target.closest(".compare-page-checkbox")) {
    miyoCheckbox.checked = !miyoCheckbox.checked;
    toggleSelection(miyoCheckbox, [miyoCheckbox, clientDatasetRightCheckbox]);
  }
});

document.getElementById("clientDatasetRight").addEventListener("click", e => {
  if (!e.target.closest(".compare-page-checkbox")) {
    clientDatasetRightCheckbox.checked = !clientDatasetRightCheckbox.checked;
    toggleSelection(clientDatasetRightCheckbox, [miyoCheckbox, clientDatasetRightCheckbox]);
  }
});

// File upload logic
fileInputUpload.addEventListener("change", e => handleFileUpload(e.target.files));

uploadItem.addEventListener("dragover", e => {
  e.preventDefault();
  uploadItem.classList.add("dragover");
});

uploadItem.addEventListener("dragleave", () => {
  uploadItem.classList.remove("dragover");
});

uploadItem.addEventListener("drop", e => {
  e.preventDefault();
  uploadItem.classList.remove("dragover");
  if (e.dataTransfer.files.length > 0) {
    handleFileUpload(e.dataTransfer.files);
  }
});

function handleFileUpload(files) {
  const uploadedFilesList = document.getElementById("uploadedFilesList");
  uploadedFilesList.innerHTML = "";

  if (files.length > 0) {
    uploadCheckbox.checked = true;
    toggleSelection(uploadCheckbox, [uploadCheckbox, clientDatasetCheckbox]);
    uploadItem.classList.add("uploaded");

    Array.from(files).forEach(file => {
      const fileType = file.name.split(".").pop().toLowerCase();
      const iconSrc = getFileIcon(fileType);

      const fileEntry = document.createElement("div");
      fileEntry.classList.add("uploaded-file-item");

      const fileIcon = document.createElement("img");
      fileIcon.src = iconSrc;
      fileIcon.alt = `${fileType} icon`;

      const fileName = document.createElement("span");
      fileName.textContent = file.name;

      const removeBtn = document.createElement("button");
      removeBtn.classList.add("uploaded-file-remove");
      removeBtn.innerHTML = "&times;";

      removeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        fileEntry.remove();

        if (uploadedFilesList.children.length === 0) {
          uploadItem.classList.remove("uploaded");
          uploadCheckbox.checked = false;
          updateButtonState();
        }
      });

      fileEntry.append(fileIcon, fileName, removeBtn);
      uploadedFilesList.appendChild(fileEntry);
    });

    showPopup("✅ File(s) uploaded successfully!");
  } else {
    uploadedFilesList.innerHTML = "";
    uploadItem.classList.remove("uploaded");
  }
}

function getFileIcon(ext) {
  switch (ext) {
    case "pdf": return "file-icons/pdf.png";
    case "doc":
    case "docx": return "file-icons/word.png";
    case "xls":
    case "xlsx": return "file-icons/excel.png";
    case "png":
    case "jpg":
    case "jpeg":
    case "gif": return "file-icons/image.png";
    case "csv": return "file-icons/excel.png";
    default: return "file-icons/folder.png";
  }
}

compareBtn.addEventListener("click", () => {
  const left = uploadCheckbox.checked ? "Upload File" : "Client Dataset";
  const right = miyoCheckbox.checked ? "MYIPO Journals" : "Client Dataset";

  // ✅ Show popup
  showPopup(`Comparing ${left} with ${right}...`);

  // ✅ Get sections
  const comparisonInfo = document.getElementById("comparisonInfo");
  const loadingSection = document.getElementById("loadingSection");
  const resultsSection = document.getElementById("resultsSection");
  const progressFill = document.querySelector(".progress-fill");
  const resultsGrid = document.querySelector(".results-grid");

  if (comparisonInfo && loadingSection && resultsSection && resultsGrid) {
    // 🧹 Reset previous results completely
    resultsSection.classList.remove("show");
    loadingSection.classList.remove("show");
    progressFill.style.width = "0%";
    resultsGrid.innerHTML = ""; // ✅ clear old result cards

    // 📝 Update info text
    comparisonInfo.textContent = `Comparing ${left} with ${right}`;

    // 🔄 Show loading
    loadingSection.classList.add("show");

    // 🪄 Scroll smoothly to loading section
    loadingSection.scrollIntoView({ behavior: "smooth", block: "start" });

    // 📈 Animate progress bar
    let progress = 0;
    const interval = setInterval(() => {
      progress += 2;
      if (progress > 100) progress = 100;
      progressFill.style.width = progress + "%";
    }, 70);

    // ⏳ Simulate comparison and show fresh results
    setTimeout(() => {
      clearInterval(interval);
      loadingSection.classList.remove("show");

      // 🧩 Generate new cards dynamically (you can adjust content later)
      const newResults = [
        { img: "icons/trademark-1.png", label: "CM LIEW ENTERPRISE SDN. BHD. ", imgSim: 70, textSim: 70 },
        { img: "icons/trademark-2.png", label: "DAPPER CORPORATION SDN. BHD. ", imgSim: 90, textSim: 30 },
        { img: "icons/trademark-3.png", label: "JOHN HOLLAND GROUP PTY LTD", imgSim: 20, textSim: 85 }
      ];

      newResults.forEach(result => {
        const card = document.createElement("div");
        card.className = "result-card";
        
        const imgClass = result.imgSim > 50 ? "high" : "low";
        const textClass = result.textSim > 50 ? "high" : "low";
        
        card.innerHTML = `
          <div class="card-top">
            <div class="card-icon"><img src="${result.img}" alt="${result.label} Icon"></div>
            <div class="card-label">${result.label}</div>
            <div class="card-similarities">
              <div class="similarity-item">
                <span class="similarity-label">Image Similarity</span>
                <span class="similarity-percentage ${imgClass}">${result.imgSim}%</span>
              </div>
              <div class="similarity-item">
                <span class="similarity-label">Text Similarity</span>
                <span class="similarity-percentage ${textClass}">${result.textSim}%</span>
              </div>
            </div>
          </div>
        `;

        // 🟢 ADD THIS — open modal on click
        card.addEventListener("click", () => openDetailModal(result));

        resultsGrid.appendChild(card);
      });


      // ✅ Show fresh result section
      resultsSection.classList.add("show");

      // Scroll to new results
      resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 3500);
  }
});

function showPopup(message, isError = false) {
  let popup = document.querySelector(".compare-page-popup");
  if (!popup) {
    popup = document.createElement("div");
    popup.className = "compare-page-popup";
    document.body.appendChild(popup);
  }
  popup.textContent = message;
  popup.classList.add("show");
  popup.classList.toggle("error", isError);
  setTimeout(() => popup.classList.remove("show"), 3000);
}

updateVisualState();
updateButtonState();

// ===== DETAIL MODAL FUNCTIONALITY =====
const detailModal = document.getElementById("detailModal");
const modalClose = document.getElementById("modalClose");

function openDetailModal(data) {
  // Fill in modal data (customize as needed)
  document.getElementById("modalImage").src = data.img;
  document.getElementById("modalCompanyName").textContent = data.label;
  document.getElementById("modalImageSim").textContent = `${data.imgSim}%`;
  document.getElementById("modalTextSim").textContent = `${data.textSim}%`;

  // Show modal
  detailModal.classList.add("show");
}

function closeDetailModal() {
  detailModal.classList.remove("show");
}

// Close button
modalClose.addEventListener("click", closeDetailModal);

// Close when clicking outside modal content
detailModal.addEventListener("click", (e) => {
  if (e.target === detailModal) closeDetailModal();
});

document.getElementById("modalDownload").addEventListener("click", () => {
  showPopup("📄 Downloading report...");
});