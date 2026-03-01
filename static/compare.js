const uploadCheckbox = document.getElementById("uploadCheckbox");
const clientDatasetCheckbox = document.getElementById("clientDatasetCheckbox");
const miyoCheckbox = document.getElementById("miyoCheckbox");
const clientDatasetRightCheckbox = document.getElementById("clientDatasetRightCheckbox");
const compareBtn = document.getElementById("compareBtn");
const uploadItem = document.getElementById("uploadItem");
const fileInputUpload = document.getElementById("fileInputUpload");
const resultsGrid = document.querySelector(".results-grid");
const detailModal = document.getElementById("detailModal");
const modalClose = document.getElementById("modalClose");

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

function renderResultCard(result) {
  const card = document.createElement("div");
  card.className = "result-card";

  const imgClass = result.imgSim > 50 ? "high" : "low";
  const textClass = result.textSim > 50 ? "high" : "low";

  card.innerHTML = `
    <div class="card-top">
      <div class="card-icon">
        <img src="/logo/${result.id}" alt="Trademark Logo">
      </div>
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
    // // Map the backend keys to what the Modal expects
    // card.addEventListener("click", () => openDetailModal({
    //     id: result.id,
    //     label: result.label,
    //     imgSim: result.imgSim,
    //     textSim: result.textSim,
    //     modalTrademarkNum: result.serial,
    //     modalDescription: result.description || "No description provided."
    // }));
  card.addEventListener("click", () => openDetailModal({
      id: result.id,
      label: result.label,
      imgSim: result.imgSim,
      textSim: result.textSim,
      modalTrademarkNum: result.serial,
      modalDescription: result.description, // Passed from Python match_list
      modalClass: result.modalClass,         // Passed from Python match_list
      modalAgent: result.modalAgent           // Passed from Python match_list
  }));
    resultsGrid.appendChild(card);
}

compareBtn.addEventListener("click", async () => {
    const isClientSource = clientDatasetCheckbox.checked;
    const sourceCategory = isClientSource ? "CLIENT" : "UPLOAD";

    const isClientTarget = clientDatasetRightCheckbox.checked;
    const targetType = isClientTarget ? "CLIENT" : "MYIPO";

    if (!isClientSource && fileInputUpload.files.length === 0) {
        showPopup("Please upload a file first!", true);
        return;
    }

    const loadingSection = document.getElementById("loadingSection");
    const resultsSection = document.getElementById("resultsSection");
    const progressFill = document.querySelector(".progress-fill");

    resultsGrid.innerHTML = "";
    resultsSection.classList.remove("show");
    loadingSection.classList.add("show");
    progressFill.style.width = "30%";

    const formData = new FormData();
    if (!isClientSource) {
        formData.append("file", fileInputUpload.files[0]);
    }
    formData.append("source_category", sourceCategory);
    formData.append("target", targetType);

    try {
        const response = await fetch("/api/perform_comparison", {
            method: "POST",
            body: formData
        });

        const results = await response.json();

        if (!response.ok || results.error) {
            throw new Error(results.error || "Comparison failed");
        }

        loadingSection.classList.remove("show");
        resultsSection.classList.add("show");

        // IMAGE upload
        if (Array.isArray(results) && results.length && !results[0].matches) {
            results.forEach(renderResultCard);
        }
        // PDF / CLIENT
        else {
            results.forEach(group => {
                group.matches.forEach(renderResultCard);
            });
        }

    } catch (error) {
        loadingSection.classList.remove("show");
        showPopup("Error: " + error.message, true);
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
// const detailModal = document.getElementById("detailModal");
// const modalClose = document.getElementById("modalClose");

// function openDetailModal(data) {
//   // 1. Update standard modal fields
//   document.getElementById("modalImage").src = `/logo/${data.id}`;
//   document.getElementById("modalCompanyName").textContent = data.label;
//   document.getElementById("modalImageSim").textContent = `${data.imgSim}%`;
//   document.getElementById("modalTextSim").textContent = `${data.textSim}%`;
//   document.getElementById("modalTrademarkNum").textContent = data.modalTrademarkNum;
//   // Ensure your modal has this ID for class if you use it, or adjust as needed
//   if(document.getElementById("modalClass")) document.getElementById("modalClass").textContent = data.modalClass || "N/A"; 
//   document.getElementById("modalDescription").textContent = data.modalDescription;

//   // 2. Clear and rebuild the Top 3 Matches list
//   const matchesList = document.getElementById("modalMatchesList");
//   matchesList.innerHTML = ""; // This removes the hardcoded Loreal items

//   if (data.matches && data.matches.length > 0) {
//     data.matches.forEach(match => {
//       const matchHtml = `
//         <div class="match-item">
//           <div class="match-left">
//             <div class="match-badge">Similarity: ${match.sim}</div>
//             <div class="match-title">${match.label}</div>
//             <div class="match-meta">Serial: ${match.serial}</div>
//             <div class="match-desc">Visually similar entry found in database.</div>
//           </div>
//           <div class="match-image">
//             <img src="/logo/${match.id}" alt="Match Logo">
//           </div>
//         </div>
//       `;
//       matchesList.insertAdjacentHTML('beforeend', matchHtml);
//     });
//   } else {
//     matchesList.innerHTML = "<p style='color: #ccc; padding: 10px;'>No other close matches found.</p>";
//   }

//   detailModal.classList.add("show");
// }
function openDetailModal(data) {
  console.log("Modal Data Received:", data);

  // 1. Image & Company Name (These are working)
  document.getElementById("modalImage").src = `/logo/${data.id}`;
  document.getElementById("modalCompanyName").textContent = data.label || "N/A";

  // 2. Similarities (These are working)
  document.getElementById("modalImageSim").textContent = `${data.imgSim}%`;
  document.getElementById("modalTextSim").textContent = `${data.textSim}%`;

  // 3. FIX: Trademark Number
  // The console shows the key is called 'modalTrademarkNum'
  document.getElementById("modalTrademarkNum").textContent = data.modalTrademarkNum || "N/A";

  // 4. Class & Agent (These are working)
  document.getElementById("modalClass").textContent = data.modalClass || "N/A";
  document.getElementById("modalAgent").textContent = data.modalAgent || "N/A";

  // 5. FIX: Description 
  // The console shows the key is called 'modalDescription'
  document.getElementById("modalDescription").textContent = data.modalDescription || "N/A";

  // 6. Show the modal
  const detailModal = document.getElementById("detailModal");
  detailModal.classList.add("show");
}

function closeDetailModal() {
  detailModal.classList.remove("show");
}

modalClose.addEventListener("click", closeDetailModal);
detailModal.addEventListener("click", (e) => { if (e.target === detailModal) closeDetailModal(); });

// Need do this to generate report
// document.getElementById("modalDownload").addEventListener("click", () => {
//   showPopup("📄 Downloading report...");
// });
document.getElementById("modalDownload").addEventListener("click", function() {
    // 1. Gather all data currently in the modal
    // We get the ID from the logo URL (e.g., /logo/26145)
    const logoSrc = document.getElementById("modalImage").src;
    const trademarkId = logoSrc.split('/').pop();

    const reportData = {
        id: trademarkId,
        label: document.getElementById("modalCompanyName").textContent,
        imgSim: document.getElementById("modalImageSim").textContent.replace('%', ''),
        textSim: document.getElementById("modalTextSim").textContent.replace('%', ''),
        serial: document.getElementById("modalTrademarkNum").textContent,
        modalClass: document.getElementById("modalClass").textContent,
        modalAgent: document.getElementById("modalAgent").textContent,
        description: document.getElementById("modalDescription").textContent
    };

    showPopup("📄 Generating professional PDF report...");

    // 2. Send to backend
    fetch('/api/generate_pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reportData)
    })
    .then(response => {
        if (!response.ok) throw new Error("PDF generation failed");
        return response.blob();
    })
    .then(blob => {
        // 3. Trigger actual browser download
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Trademark_Report_${reportData.serial}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
    })
    .catch(err => {
        console.error(err);
        showPopup("❌ Error generating PDF");
    });
});

document.querySelectorAll('.match-badge').forEach(badge => {
  const matchText = badge.textContent;
  const matchValue = parseFloat(matchText.match(/([\d.]+)%/)[1]); // extract number before '%'
  
  if (matchValue > 50) {
    badge.classList.add('high'); // red
  } else {
    badge.classList.remove('high'); // light grey
  }
});


