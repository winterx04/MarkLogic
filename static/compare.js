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

function renderResultCard(result, allMatches) {
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

  // PASS BOTH the specific result and the full list of matches to the modal
  card.addEventListener("click", () => openDetailModal(result, allMatches));
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
            results.forEach(res => renderResultCard(res, results));
        }
        // PDF / CLIENT
        else {
            results.forEach(group => {
                // We pass group.matches as the second argument here
                group.matches.forEach(res => renderResultCard(res, group.matches));
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
function openDetailModal(data, allMatches = []) {
  // --- Check if data is exists and getting fetched correctly ---
  console.log("Modal Data Received:", data);
  // --- CLARIFICATION LOGS ---
  console.group("🔍 Score Calculation Breakdown");
  console.log(`Company: ${data.label}`);
  console.log(`1. Image Similarity (AI): ${data.imgSim}%`);
  console.log(`2. Text Similarity (AI + Literal): ${data.textSim}%`);
  console.log(`3. Final Weighted Match Score: ${data.totalSim}%`);
  console.log("Calculation Logic: (Literal Match * 0.4) + (Text AI * 0.4) + (Image AI * 0.2)");
  console.groupEnd();

  if (allMatches.length > 0) {
      console.log("📊 Top 3 Matches Raw Data:", allMatches.slice(0, 3));
  }
  // 1. Fill main fields
  document.getElementById("modalImage").src = `/logo/${data.id}`;
  document.getElementById("modalCompanyName").textContent = data.label || "N/A";
  document.getElementById("modalImageSim").textContent = `${data.imgSim}%`;
  document.getElementById("modalTextSim").textContent = `${data.textSim}%`;
  document.getElementById("modalTrademarkNum").textContent = data.serial || data.modalTrademarkNum || "N/A";
  document.getElementById("modalClass").textContent = data.modalClass || "N/A";
  document.getElementById("modalAgent").textContent = data.modalAgent || "N/A";
  document.getElementById("modalDescription").textContent = data.description || data.modalDescription || "N/A";

  // 2. Populate Top 3 Matches List
  const matchesList = document.getElementById("modalMatchesList");
  matchesList.innerHTML = ""; // Clear existing

  // Filter out the current item so it doesn't show itself as a match
  const others = allMatches.filter(m => m.id !== data.id).slice(0, 3);

  if (others.length === 0) {
    matchesList.innerHTML = "<p style='color: #888; padding: 10px; font-style: italic;'>No other similar matches found.</p>";
  } else {
    others.forEach(m => {
      const matchItem = document.createElement("div");
      matchItem.className = "modal-match-row"; 
      // Add inline styles for a clean list look
      matchItem.style = "display: flex; align-items: center; gap: 15px; padding: 12px; border-bottom: 1px solid #eee; cursor: pointer; transition: background 0.2s;";
      
      matchItem.innerHTML = `
        <img src="/logo/${m.id}" style="width: 45px; height: 45px; object-fit: contain; background: #fff; border: 1px solid #ddd; border-radius: 4px;">
        <div style="flex: 1;">
          <div style="font-weight: 600; font-size: 0.9rem; color: #333;">${m.label}</div>
          <div style="font-size: 0.8rem; color: #666;">${m.serial || m.modalTrademarkNum}</div>
        </div>
        <div style="text-align: right;">
          <div style="font-weight: bold; color: #4f46e5;">${m.totalSim}%</div>
          <div style="font-size: 0.7rem; color: #999;">Match Score</div>
        </div>
      `;

      // Allow user to click a "Top 3" item to switch the modal to that trademark
      matchItem.addEventListener("click", (e) => {
        e.stopPropagation();
        openDetailModal(m, allMatches);
      });

      // Hover effect
      matchItem.onmouseenter = () => matchItem.style.background = "#f1f5f9";
      matchItem.onmouseleave = () => matchItem.style.background = "transparent";

      matchesList.appendChild(matchItem);
    });
  }

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

// ── Helpers ──────────────────────────────────────────────────
    const IMG_BASE    = 'static/images/';
    const PLACEHOLDER = IMG_BASE + 'trademark-placeholder.png';

    /**
     * Build an <img> tag for a trademark image.
     * All entries use the shared placeholder until real images are supplied.
     * To swap in a real image, change the `img` field on the data object to
     * the actual filename (with extension), e.g. "TM-001.png" or "my-mark.jpg".
     *
     * @param {string} imgFile - Filename with extension, or null/undefined to use placeholder
     * @param {string} alt     - Alt text
     */
    function tmImg(imgFile, alt) {
      const src = imgFile ? IMG_BASE + imgFile : PLACEHOLDER;
      return `<img src="${src}" alt="${alt}"
                   style="width:100%;height:100%;object-fit:contain;padding:6px;"
                   onerror="this.src='${PLACEHOLDER}'">`;
    }

    // ── State ──────────────────────────────────────────────────
    let selectedSource  = null;   // 'upload' | 'clientLeft'
    let selectedCompare = null;   // 'clientRight' | 'myipo'
    let uploadedFiles   = [];
    let threshold       = 70;
    let currentMode     = 'image'; // 'image' | 'pdf'

    const sourceMap  = { upload: 'uploadCheckbox',           clientLeft:  'clientDatasetCheckbox' };
    const compareMap = { clientRight: 'clientDatasetRightCheckbox', myipo: 'miyoCheckbox' };
    const itemEls    = { upload: 'uploadItem', clientLeft: 'clientDatasetLeft',
                         clientRight: 'clientDatasetRight', myipo: 'miyoItem' };

    // ── Mock data ───────────────────────────────────────────────
    // Each entry now uses an `img` field (filename without extension)
    // instead of an emoji.  Images live in static/images/<img>.png
    const mockImageResults = [
      { id:'TM-001', img:null, company:'CircleBrand Sdn Bhd', imageSim:94, textSim:88,
        tmNum:'2021003456', cls:'35', agent:'IP Partners MY', desc:'Brand mark for retail services.' },
      { id:'TM-002', img:null, company:'Alpha Script Co',     imageSim:87, textSim:72,
        tmNum:'2020001122', cls:'42', agent:'CM Liew Enterprise', desc:'Stylised letter mark for software.' },
      { id:'TM-003', img:null, company:'Shield Corp',         imageSim:81, textSim:79,
        tmNum:'2019005678', cls:'16', agent:'Khoo & Associates',  desc:'Heraldic shield for printed materials.' },
      { id:'TM-004', img:null, company:'Waveline Sdn Bhd',    imageSim:76, textSim:65,
        tmNum:'2022007890', cls:'38', agent:'TM Agents MY',       desc:'Wave pattern for telecoms.' },
      { id:'TM-005', img:null, company:'StarBurst Industries', imageSim:73, textSim:55,
        tmNum:'2018009012', cls:'11', agent:'Law & IP Firm',      desc:'Star burst icon for lighting.' },
      { id:'TM-006', img:null, company:'Trimark Holdings',    imageSim:71, textSim:68,
        tmNum:'2023001234', cls:'36', agent:'IP Registry MY',     desc:'Triangle for financial services.' },
      { id:'TM-007', img:null, company:'Oval Creative',       imageSim:64, textSim:71,
        tmNum:'2021008765', cls:'41', agent:'Marks Global',       desc:'Oval device for education.' },
      { id:'TM-008', img:null, company:'Delta Group',         imageSim:55, textSim:60,
        tmNum:'2017004321', cls:'44', agent:'Delta IP Sdn Bhd',   desc:'Delta symbol for medical.' },
    ];

    const mockPDFResults = [
      { id:'TM-S1-01', img:null, label:'Circular Logo Mark', matches:[
          { id:'TM-S2-03', img:null, label:'Round Badge Mark',  imageSim:94, textSim:88, tmNum:'2021003456', cls:'35', agent:'IP Partners MY',   desc:'Round badge for retail.' },
          { id:'TM-S2-07', img:null, label:'Circle Brand Icon', imageSim:82, textSim:74, tmNum:'2020009876', cls:'42', agent:'CM Liew',           desc:'Circle icon for tech.' },
          { id:'TM-S2-11', img:null, label:'Oval Emblem',       imageSim:73, textSim:61, tmNum:'2019003214', cls:'16', agent:'Khoo & Assoc',      desc:'Oval device.' },
          { id:'TM-S2-14', img:null, label:'Disc Symbol',       imageSim:61, textSim:55, tmNum:'2022001122', cls:'38', agent:'TM Agents',         desc:'Disc symbol.' },
        ]},
      { id:'TM-S1-02', img:null, label:'Stylized Letter "A"', matches:[
          { id:'TM-S2-01', img:null, label:'Angled "A" Mark',   imageSim:91, textSim:83, tmNum:'2020001122', cls:'42', agent:'CM Liew Enterprise', desc:'Stylised A.' },
          { id:'TM-S2-09', img:null, label:'Alpha Symbol',      imageSim:78, textSim:69, tmNum:'2021007654', cls:'35', agent:'Alpha IP',           desc:'Alpha symbol mark.' },
          { id:'TM-S2-12', img:null, label:'Script Letter A',   imageSim:65, textSim:59, tmNum:'2018005432', cls:'41', agent:'Script Marks',       desc:'Script A device.' },
        ]},
      { id:'TM-S1-03', img:null, label:'Shield Emblem', matches:[
          { id:'TM-S2-05', img:null, label:'Crest Shield',      imageSim:88, textSim:80, tmNum:'2019005678', cls:'16', agent:'Khoo & Associates',  desc:'Crest shield.' },
          { id:'TM-S2-08', img:null, label:'Heraldic Badge',    imageSim:75, textSim:67, tmNum:'2022003456', cls:'36', agent:'IP Registry',        desc:'Heraldic badge.' },
          { id:'TM-S2-13', img:null, label:'Armour Plate Logo', imageSim:55, textSim:48, tmNum:'2017008765', cls:'44', agent:'Delta IP',           desc:'Armour plate.' },
        ]},
      { id:'TM-S1-04', img:null, label:'Wave Pattern', matches:[
          { id:'TM-S2-02', img:null, label:'Flowing Curve',     imageSim:86, textSim:78, tmNum:'2022007890', cls:'38', agent:'TM Agents MY',       desc:'Flowing wave.' },
          { id:'TM-S2-06', img:null, label:'Ripple Mark',       imageSim:71, textSim:63, tmNum:'2021009012', cls:'11', agent:'Law & IP Firm',      desc:'Ripple device.' },
        ]},
      { id:'TM-S1-05', img:null, label:'Star Burst Icon', matches:[
          { id:'TM-S2-10', img:null, label:'Radiant Star',      imageSim:58, textSim:52, tmNum:'2018009012', cls:'11', agent:'Law & IP Firm',      desc:'Star burst.' },
          { id:'TM-S2-15', img:null, label:'Sun Burst Logo',    imageSim:53, textSim:47, tmNum:'2020004321', cls:'44', agent:'Delta IP',           desc:'Sun burst device.' },
        ]},
      { id:'TM-S1-06', img:null, label:'Abstract Triangle', matches:[
          { id:'TM-S2-04', img:null, label:'Tri-Form Mark',     imageSim:97, textSim:91, tmNum:'2023001234', cls:'36', agent:'IP Registry MY',     desc:'Tri-form mark.' },
          { id:'TM-S2-16', img:null, label:'Pyramid Symbol',    imageSim:89, textSim:82, tmNum:'2021005678', cls:'35', agent:'IP Partners',        desc:'Pyramid symbol.' },
          { id:'TM-S2-17', img:null, label:'Angular Logo',      imageSim:76, textSim:68, tmNum:'2019007890', cls:'42', agent:'CM Liew',            desc:'Angular device.' },
          { id:'TM-S2-18', img:null, label:'Delta Icon',        imageSim:68, textSim:60, tmNum:'2022009012', cls:'38', agent:'TM Agents',          desc:'Delta icon.' },
        ]},
    ];

    // ── Selection helpers ────────────────────────────────────────
    function handleItemClick(key, e) {
      if (e.target.type === 'checkbox') return;
      if (key === 'upload') {
        document.getElementById('fileInputUpload').click();
        return;
      }
      if (key in sourceMap) toggleSource(key);
      else toggleCompare(key);
    }
    function handleCheckbox(key) {
      if (key === 'upload') {
        if (uploadedFiles.length === 0) {
          document.getElementById('fileInputUpload').click();
        } else {
          toggleSource('upload');
        }
        return;
      }
      if (key in sourceMap) toggleSource(key);
      else toggleCompare(key);
    }

    function toggleSource(key) {
      if (selectedSource === key) { selectedSource = null; }
      else {
        if (selectedSource) {
          document.getElementById(sourceMap[selectedSource]).checked = false;
          document.getElementById(itemEls[selectedSource]).classList.remove('selected');
        }
        selectedSource = key;
      }
      const checked = selectedSource === key;
      document.getElementById(sourceMap[key]).checked = checked;
      document.getElementById(itemEls[key]).classList.toggle('selected', checked);
      updateCompareBtn();
    }

    function toggleCompare(key) {
      if (selectedCompare === key) { selectedCompare = null; }
      else {
        if (selectedCompare) {
          document.getElementById(compareMap[selectedCompare]).checked = false;
          document.getElementById(itemEls[selectedCompare]).classList.remove('selected');
        }
        selectedCompare = key;
      }
      const checked = selectedCompare === key;
      document.getElementById(compareMap[key]).checked = checked;
      document.getElementById(itemEls[key]).classList.toggle('selected', checked);
      updateCompareBtn();
    }

    function updateCompareBtn() {
      document.getElementById('compareBtn').disabled = !(selectedSource && selectedCompare);
    }

    // ── Drag & Drop ──────────────────────────────────────────────
    function handleDragOver(e, id) {
      e.preventDefault();
      document.getElementById(id).classList.add('dragover');
    }
    function handleDragLeave(id) {
      document.getElementById(id).classList.remove('dragover');
    }
    function handleDrop(e, id) {
      e.preventDefault();
      document.getElementById(id).classList.remove('dragover');
      processFiles(Array.from(e.dataTransfer.files));
    }

    // ── File Upload ──────────────────────────────────────────────
    function handleFileUpload(e) {
      const files = Array.from(e.target.files);
      e.target.value = '';
      processFiles(files);
    }

    function processFiles(files) {
      if (files.length > 0) uploadedFiles = [files[0]];
      currentMode = uploadedFiles.some(f => f.name.toLowerCase().endsWith('.pdf')) ? 'pdf' : 'image';
      renderUploadPreviews();
      if (uploadedFiles.length > 0 && selectedSource !== 'upload') toggleSource('upload');
    }

    function renderUploadPreviews() {
      const grid  = document.getElementById('uploadPreviewGrid');
      const count = document.getElementById('uploadFileCount');
      const item  = document.getElementById('uploadItem');

      if (uploadedFiles.length === 0) {
        grid.innerHTML    = '';
        count.textContent = '';
        item.classList.remove('has-files');
        return;
      }

      item.classList.add('has-files');
      const file  = uploadedFiles[0];
      const isPDF = file.name.toLowerCase().endsWith('.pdf');

      count.textContent = file.name;
      grid.innerHTML    = '';

      const tile = document.createElement('div');
      tile.className = 'upload-preview-tile';

      if (isPDF) {
        tile.innerHTML = `
          <div class="pdf-preview-tile-inner">
            <span class="pdf-icon">📄</span>
            <span class="pdf-name">${file.name}</span>
          </div>
          <button class="preview-remove-btn" title="Remove" onclick="removeFile(event)">✕</button>`;
      } else {
        const img = document.createElement('img');
        img.className = 'preview-img';
        img.alt   = file.name;
        img.title = file.name;
        const reader = new FileReader();
        reader.onload = e => { img.src = e.target.result; };
        reader.readAsDataURL(file);

        const removeBtn       = document.createElement('button');
        removeBtn.className   = 'preview-remove-btn';
        removeBtn.title       = 'Remove';
        removeBtn.textContent = '✕';
        removeBtn.onclick     = ev => removeFile(ev);

        tile.appendChild(img);
        tile.appendChild(removeBtn);
      }
      grid.appendChild(tile);

      const changeBtn       = document.createElement('button');
      changeBtn.className   = 'upload-change-link';
      changeBtn.textContent = 'Change file';
      changeBtn.onclick = e => {
        e.stopPropagation();
        document.getElementById('fileInputUpload').click();
      };
      grid.appendChild(changeBtn);
    }

    function removeFile(e) {
      e.stopPropagation();
      uploadedFiles = [];
      renderUploadPreviews();
      if (selectedSource === 'upload') toggleSource('upload');
    }

    // ── Run Compare ──────────────────────────────────────────────
    function runCompare() {
      if (selectedSource === 'upload' && uploadedFiles.length > 0) {
        currentMode = uploadedFiles.some(f => f.name.toLowerCase().endsWith('.pdf')) ? 'pdf' : 'image';
      } else {
        currentMode = 'pdf';
      }

      const srcLabel = selectedSource === 'upload' ? 'Uploaded File' : 'Client Dataset';
      const cmpLabel = selectedCompare === 'myipo' ? 'MYIPO Journals' : 'Client Dataset';
      document.getElementById('comparisonInfo').textContent = `Comparing ${srcLabel} with ${cmpLabel}`;
      document.getElementById('filterNote').textContent = `Showing ≥ ${threshold}%`;

      const ls = document.getElementById('loadingSection');
      const rs = document.getElementById('resultsSection');
      ls.classList.add('show');
      rs.classList.remove('show');
      document.getElementById('resetBtn').style.display = 'none';

      setTimeout(() => {
        ls.classList.remove('show');
        renderResults();
        rs.classList.add('show');
        document.getElementById('resetBtn').style.display = 'inline-flex';
        rs.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 2400);
    }

    // ── Reset ────────────────────────────────────────────────────
    function resetCompare() {
      selectedSource  = null;
      selectedCompare = null;
      uploadedFiles   = [];
      currentMode     = 'image';

      Object.values(sourceMap).forEach(id  => { document.getElementById(id).checked = false; });
      Object.values(compareMap).forEach(id => { document.getElementById(id).checked = false; });
      Object.values(itemEls).forEach(id    => { document.getElementById(id).classList.remove('selected'); });

      renderUploadPreviews();

      document.getElementById('resultsSection').classList.remove('show');
      document.getElementById('loadingSection').classList.remove('show');
      document.getElementById('compareBtn').disabled = true;
      document.getElementById('resetBtn').style.display = 'none';

      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ── Render ───────────────────────────────────────────────────
    function renderResults() {
      currentMode === 'image' ? renderImageMode() : renderPDFMode();
    }

    function renderImageMode() {
      document.getElementById('sourceBlocks').innerHTML = '';
      const filtered = mockImageResults.filter(r => r.imageSim >= threshold);
      document.getElementById('resultsCount').textContent =
        `${filtered.length} match${filtered.length !== 1 ? 'es' : ''}`;

      document.getElementById('resultsGrid').innerHTML = filtered.map((r, i) => {
        const high     = r.imageSim >= 80;
        const pctClass = high ? 'high' : 'low';
        const imgTag   = tmImg(r.img, r.company);
        return `
        <div class="result-card" style="animation-delay:${i * 0.08}s; cursor:pointer;"
             onclick='openModal(${JSON.stringify(r).replace(/'/g,"&#39;")})'>
          <div class="card-top">
            <div class="card-icon-img">${imgTag}</div>
            <div class="card-similarities">
              <div class="similarity-item">
                <span class="similarity-label">Image Similarity</span>
                <span class="similarity-percentage ${pctClass}">${r.imageSim}%</span>
                <div class="sim-bar-bg"><div class="sim-bar-fill${high ? ' danger' : ''}" style="width:${r.imageSim}%"></div></div>
              </div>
              <div class="similarity-item">
                <span class="similarity-label">Text Similarity</span>
                <span class="similarity-percentage ${r.textSim >= 80 ? 'high' : 'low'}">${r.textSim}%</span>
                <div class="sim-bar-bg"><div class="sim-bar-fill${r.textSim >= 80 ? ' danger' : ''}" style="width:${r.textSim}%"></div></div>
              </div>
            </div>
            <div class="card-label">${r.company}</div>
          </div>
        </div>`;
      }).join('');
    }

    function renderPDFMode() {
      document.getElementById('resultsGrid').innerHTML = '';
      let totalMatches = 0;
      const cmpLabel = selectedCompare === 'myipo' ? 'MYIPO Journals' : 'Client Dataset';

      document.getElementById('sourceBlocks').innerHTML = mockPDFResults.map((src, bi) => {
        const filtered = src.matches.filter(m => m.imageSim >= threshold);
        totalMatches  += filtered.length;

        const hasCls   = filtered.length > 0 ? 'has-matches' : '';
        const badgeTxt = filtered.length > 0
          ? `${filtered.length} match${filtered.length > 1 ? 'es' : ''} found`
          : 'No matches above threshold';

        const inner = filtered.length === 0
          ? `<div class="no-match-msg">No images from ${cmpLabel} are above ${threshold}% for this trademark.</div>`
          : `<div class="match-list">
              <div class="match-list-label">↳ Matches from ${cmpLabel}</div>
              ${filtered.map(m => {
                const avg     = Math.round((m.imageSim + m.textSim) / 2);
                const high    = avg >= 80;
                const pillCls = high ? 'high' : 'mid';
                const mJson   = JSON.stringify(m).replace(/'/g,"&#39;");
                return `
                <div class="match-row" onclick='openModal(${mJson})'>
                  <div class="match-thumb">${tmImg(m.img, m.label)}</div>
                  <div class="match-info">
                    <div class="match-name">${m.id} — ${m.label}</div>
                    <div style="display:flex;flex-direction:column;gap:5px;margin-top:4px;">
                      <div style="display:flex;align-items:center;gap:8px;">
                        <span style="font-size:10px;color:rgba(255,255,255,0.45);width:38px;flex-shrink:0;">Image</span>
                        <div class="mini-bar-bg" style="flex:1;">
                          <div class="mini-bar-fill ${m.imageSim >= 80 ? 'fill-high' : 'fill-mid'}" style="width:${m.imageSim}%"></div>
                        </div>
                        <span style="font-size:11px;font-weight:600;color:${m.imageSim >= 80 ? '#ff8a8a' : '#6EE0F5'};width:32px;text-align:right;flex-shrink:0;">${m.imageSim}%</span>
                      </div>
                      <div style="display:flex;align-items:center;gap:8px;">
                        <span style="font-size:10px;color:rgba(255,255,255,0.45);width:38px;flex-shrink:0;">Text</span>
                        <div class="mini-bar-bg" style="flex:1;">
                          <div class="mini-bar-fill ${m.textSim >= 80 ? 'fill-high' : 'fill-mid'}" style="width:${m.textSim}%"></div>
                        </div>
                        <span style="font-size:11px;font-weight:600;color:${m.textSim >= 80 ? '#ff8a8a' : '#6EE0F5'};width:32px;text-align:right;flex-shrink:0;">${m.textSim}%</span>
                      </div>
                    </div>
                  </div>
                  <span class="score-pill ${pillCls}" title="Avg of image & text similarity">${avg}%</span>
                </div>`;
              }).join('')}
            </div>`;

        return `
        <div class="source-block" style="animation-delay:${bi * 0.07}s;">
          <div class="source-block-header">
            <div class="source-thumb">${tmImg(src.img, src.label)}</div>
            <div class="source-meta">
              <div class="tm-id">${src.id}</div>
              <div class="tm-label">${src.label} — Source File</div>
            </div>
            <span class="match-count-badge ${hasCls}">${badgeTxt}</span>
          </div>
          ${inner}
        </div>`;
      }).join('');

      document.getElementById('resultsCount').textContent =
        `${totalMatches} total match${totalMatches !== 1 ? 'es' : ''}`;
    }

    // ── Modal ────────────────────────────────────────────────────
    function openModal(data) {
      const wrap = document.getElementById('modalImageWrap');
      const imgId = data.img || data.id;
      wrap.innerHTML = `<img class="tm-img" src="${IMG_BASE}${imgId}.png" alt="${data.company || data.label || data.id}"
                             style="width:100%;height:100%;object-fit:contain;"
                             onerror="this.src='${PLACEHOLDER}'">`;

      document.getElementById('modalCompanyName').textContent   = data.company || data.label || data.id;
      document.getElementById('modalImageSim').textContent      = data.imageSim ? data.imageSim + '%' : '—';
      document.getElementById('modalTextSim').textContent       = data.textSim  ? data.textSim  + '%' : '—';
      document.getElementById('modalTrademarkNum').textContent  = data.tmNum || '—';
      document.getElementById('modalClass').textContent         = data.cls   || '—';
      document.getElementById('modalAgent').textContent         = data.agent || '—';
      document.getElementById('modalDescription').textContent   = data.desc  || '—';

      // Top 3 nearest matches
      const pool = currentMode === 'image'
        ? mockImageResults
        : mockPDFResults.flatMap(s => s.matches);

      const others = pool
        .filter(x => x.id !== data.id)
        .sort((a, b) => Math.abs(b.imageSim - data.imageSim) - Math.abs(a.imageSim - data.imageSim))
        .slice(0, 3);

      document.getElementById('modalMatchesList').innerHTML = others.map(m => `
        <div class="match-item">
          <div class="match-left">
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
              <div class="match-badge${m.imageSim >= 70 ? ' high' : ''}">Image: ${m.imageSim}%</div>
              <div class="match-badge${m.textSim  >= 70 ? ' high' : ''}">Text: ${m.textSim}%</div>
            </div>
            <div class="match-title">${m.id} — ${m.label || m.company}</div>
            <div class="match-meta">TM No: ${m.tmNum || '—'} &nbsp;|&nbsp; Class: ${m.cls || '—'}</div>
            <div class="match-desc">${m.desc || ''}</div>
          </div>
          <div class="match-image">
            <img src="${IMG_BASE}${m.img || m.id}.png" alt="${m.label || m.company || m.id}"
                 style="width:56px;height:56px;object-fit:contain;border-radius:8px;background:rgba(255,255,255,0.08);padding:4px;"
                 onerror="this.src='${PLACEHOLDER}'">
          </div>
        </div>`).join('');

      document.getElementById('detailModal').classList.add('show');
    }

    function closeModal() {
      document.getElementById('detailModal').classList.remove('show');
    }

    document.getElementById('detailModal').addEventListener('click', function(e) {
      if (e.target === this) closeModal();
    });

    // ── Popup helper ─────────────────────────────────────────────
    function showPopup(msg, isError = false) {
      const el = document.getElementById('comparePopup');
      el.textContent = msg;
      el.className = 'compare-page-popup show' + (isError ? ' error' : '');
      setTimeout(() => { el.classList.remove('show'); }, 3000);
    }