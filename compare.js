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

        // Create container
        const fileEntry = document.createElement("div");
        fileEntry.classList.add("uploaded-file-item");

        // File icon
        const fileIcon = document.createElement("img");
        fileIcon.src = iconSrc;
        fileIcon.alt = `${fileType} icon`;

        // File name
        const fileName = document.createElement("span");
        fileName.textContent = file.name;

        // Remove button
        const removeBtn = document.createElement("button");
        removeBtn.classList.add("uploaded-file-remove");
        removeBtn.innerHTML = "&times;"; // X symbol

        removeBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            fileEntry.remove();

            // If no more files remain, reset UI
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
    showPopup(`✅ Comparing ${left} with ${right}!`);
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