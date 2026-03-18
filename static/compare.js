/**
 * STATE MANAGEMENT
 */
let selectedSource = null;   // 'upload' | 'clientLeft'
let selectedCompare = null;  // 'clientRight' | 'myipo'
let uploadedFiles = [];      // Stores the File objects
let currentMode = 'image';   // 'image' | 'pdf' based on file type
let lastComparisonResults = []; // To store API response for rendering/filtering
let modalTopMatches = [];      // To store top matches for modal navigation
 
const sourceMap = { upload: 'uploadCheckbox', clientLeft: 'clientDatasetCheckbox' };
const compareMap = { clientRight: 'clientDatasetRightCheckbox', myipo: 'miyoCheckbox' };
const itemEls = { upload: 'uploadItem', clientLeft: 'clientDatasetLeft', clientRight: 'clientDatasetRight', myipo: 'miyoItem' };

/**
 * INITIALIZATION
 */
document.addEventListener('DOMContentLoaded', () => {
    updateCompareBtn();
});

/**
 * SELECTION LOGIC
 */
function handleItemClick(key, e) {
    if (e.target.type === 'checkbox') return;
    if (key === 'upload' && uploadedFiles.length === 0) {
        document.getElementById('fileInputUpload').click();
        return;
    }
    if (key in sourceMap) toggleSource(key);
    else toggleCompare(key);
}

function handleCheckbox(key) {
    if (key === 'upload' && uploadedFiles.length === 0) {
        document.getElementById('fileInputUpload').click();
    } else {
        key in sourceMap ? toggleSource(key) : toggleCompare(key);
    }
}

function toggleSource(key) {
    if (selectedSource === key) {
        selectedSource = null;
    } else {
        if (selectedSource) {
            document.getElementById(sourceMap[selectedSource]).checked = false;
            document.getElementById(itemEls[selectedSource]).classList.remove('selected');
        }
        selectedSource = key;
    }
    const isChecked = selectedSource === key;
    document.getElementById(sourceMap[key]).checked = isChecked;
    document.getElementById(itemEls[key]).classList.toggle('selected', isChecked);
    updateCompareBtn();
}

function toggleCompare(key) {
    if (selectedCompare === key) {
        selectedCompare = null;
    } else {
        if (selectedCompare) {
            document.getElementById(compareMap[selectedCompare]).checked = false;
            document.getElementById(itemEls[selectedCompare]).classList.remove('selected');
        }
        selectedCompare = key;
    }
    const isChecked = selectedCompare === key;
    document.getElementById(compareMap[key]).checked = isChecked;
    document.getElementById(itemEls[key]).classList.toggle('selected', isChecked);
    updateCompareBtn();
}

function updateCompareBtn() {
    const btn = document.getElementById('compareBtn');
    const hasSource = selectedSource === 'clientLeft' || (selectedSource === 'upload' && uploadedFiles.length > 0);
    const hasCompare = !!selectedCompare;
    btn.disabled = !(hasSource && hasCompare);
}

/**
 * FILE UPLOAD & DRAG/DROP
 */
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

function handleFileUpload(e) {
    processFiles(Array.from(e.target.files));
    e.target.value = ''; // Reset input
}

function processFiles(files) {
    if (files.length > 0) {
        uploadedFiles = [files[0]]; // Handle one file for now
        const fileName = files[0].name.toLowerCase();
        currentMode = fileName.endsWith('.pdf') ? 'pdf' : 'image';
        
        renderUploadPreviews();
        if (selectedSource !== 'upload') toggleSource('upload');
        showPopup("✅ File uploaded successfully!");
    }
}

function renderUploadPreviews() {
    const grid = document.getElementById('uploadPreviewGrid');
    const count = document.getElementById('uploadFileCount');
    const item = document.getElementById('uploadItem');

    if (!grid || !count || !item) {
        console.warn("Upload preview elements not found in DOM.");
        return;
    }

    if (uploadedFiles.length === 0) {
        grid.innerHTML = '';
        count.textContent = '';
        item.classList.remove('has-files');
        return;
    }

    item.classList.add('has-files');
    const file = uploadedFiles[0];
    count.textContent = file.name;
    grid.innerHTML = '';

    const tile = document.createElement('div');
    tile.className = 'upload-preview-tile';

    if (currentMode === 'pdf') {
        tile.innerHTML = `
            <div class="pdf-preview-tile-inner"><span class="pdf-icon">📄</span></div>
            <button class="preview-remove-btn" onclick="removeFile(event)">✕</button>`;
    } else {
        const img = document.createElement('img');
        img.className = 'preview-img';
        const reader = new FileReader();
        reader.onload = e => img.src = e.target.result;
        reader.readAsDataURL(file);
        
        const removeBtn = document.createElement('button');
        removeBtn.className = 'preview-remove-btn';
        removeBtn.innerHTML = '✕';
        removeBtn.onclick = removeFile;
        
        tile.appendChild(img);
        tile.appendChild(removeBtn);
    }
    grid.appendChild(tile);
}

function removeFile(e) {
    e.stopPropagation();
    uploadedFiles = [];
    renderUploadPreviews();
    if (selectedSource === 'upload') toggleSource('upload');
}

/**
 * API EXECUTION (THE CORE)
 */
async function runCompare() {
    const loadingSection = document.getElementById("loadingSection");
    const resultsSection = document.getElementById("resultsSection");
    const progressFill = document.querySelector(".progress-fill");
    const resetBtn = document.getElementById("resetBtn");

    // UI Prep
    resultsSection.classList.remove("show");
    loadingSection.classList.add("show");
    progressFill.style.width = "30%";
    resetBtn.style.display = "none";

    const formData = new FormData();
    if (selectedSource === 'upload') {
        formData.append("file", uploadedFiles[0]);
        formData.append("source_category", "UPLOAD");
    } else if (selectedSource === 'clientLeft') {
        formData.append("source_category", "CLIENT");
    }
    
    const targetType = selectedCompare === 'myipo' ? "MYIPO" : "CLIENT";
    formData.append("target", targetType);

    try {
        const response = await fetch("/api/perform_comparison", {
            method: "POST",
            body: formData
        });

        const results = await response.json();
        if (!response.ok || results.error) throw new Error(results.error || "Comparison failed");

        lastComparisonResults = results;
        
        // Final UI Updates
        progressFill.style.width = "100%";
        setTimeout(() => {
            loadingSection.classList.remove("show");
            renderResults(results);
            resultsSection.classList.add("show");
            resetBtn.style.display = "inline-flex";
            resultsSection.scrollIntoView({ behavior: 'smooth' });
        }, 500);

    } catch (error) {
        loadingSection.classList.remove("show");
        showPopup("Error: " + error.message, true);
    }
}

/**
 * HELPER: Determines which URL to use based on the target selected
 */
function getLogoUrl(id) {
    if (selectedCompare === 'clientRight') {
        return `/client-logo/${id}`;
    }
    return `/logo/${id}`;
}


/**
 * RENDERING RESULTS
 */
function renderResults(data) {
    const srcLabel = selectedSource === 'upload' ? 'Uploaded File' : 'Client Dataset';
    const cmpLabel = selectedCompare === 'myipo' ? 'MYIPO Journals' : 'Client Dataset';
    document.getElementById('comparisonInfo').textContent = `Comparing ${srcLabel} with ${cmpLabel}`;

    const isGrouped = Array.isArray(data) && data.length > 0 && data[0].matches;

    if (isGrouped) {
        renderPDFMode(data);
    } else {
        renderImageMode(data);
    }
}

function renderImageMode(results) {
    const grid = document.getElementById('resultsGrid');
    document.getElementById('sourceBlocks').innerHTML = '';
    grid.innerHTML = '';
    
    document.getElementById('resultsCount').textContent = `${results.length} matches found`;

    results.forEach((res, i) => {
        const high = res.imgSim >= 80;
        const card = document.createElement('div');
        card.className = 'result-card';
        card.style.animationDelay = `${i * 0.05}s`;
        const imgSrc = getLogoUrl(res.id);
        card.innerHTML = `
            <div class="card-top">
                <div class="card-icon-img">
                    <img src="${imgSrc}" onerror="this.src='/static/images/placeholder.png'">
                </div>
                <div class="card-similarities">
                    <div class="similarity-item">
                        <span class="similarity-label">Image Similarity</span>
                        <span class="similarity-percentage ${high ? 'high' : 'low'}">${res.imgSim}%</span>
                    </div>
                    <div class="similarity-item">
                        <span class="similarity-label">Text Similarity</span>
                        <span class="similarity-percentage ${res.textSim >= 80 ? 'high' : 'low'}">${res.textSim}%</span>
                    </div>
                </div>
                <div class="card-label">${res.label}</div>
            </div>`;
        card.onclick = () => openModal(res, results);
        grid.appendChild(card);
    });
}

function renderPDFMode(groups) {
    const sourceBlocks = document.getElementById('sourceBlocks');
    if (!sourceBlocks) return;
    
    document.getElementById('resultsGrid').innerHTML = '';
    sourceBlocks.innerHTML = '';

    let totalMatches = 0;

    groups.forEach((group, bi) => {
        totalMatches += group.matches.length;
        const block = document.createElement('div');
        block.className = 'source-block';
        block.style.animationDelay = `${bi * 0.07}s`;

        const header = document.createElement('div');
        header.className = 'source-block-header';
        header.innerHTML = `
            <div class="source-meta"><div class="tm-label">Source Item #${bi + 1}</div></div>
            <span class="match-count-badge has-matches">${group.matches.length} matches</span>`;
        
        const matchList = document.createElement('div');
        matchList.className = 'match-list';

        group.matches.forEach(m => {
            const row = document.createElement('div');
            row.className = 'match-row';
            row.onclick = () => openModal(m, group.matches);
            const imgSrc = getLogoUrl(m.id);
            row.innerHTML = `
                <div class="match-thumb"><img src="${imgSrc}"></div>
                <div class="match-info">
                    <div class="match-name">${m.label}</div>
                    <div class="match-meta">Score: ${m.totalSim}%</div>
                </div>
                <span class="score-pill ${m.totalSim >= 80 ? 'high' : 'mid'}">${m.totalSim}%</span>`;
            matchList.appendChild(row);
        });

        block.appendChild(header);
        block.appendChild(matchList);
        sourceBlocks.appendChild(block);
    });
    document.getElementById('resultsCount').textContent = `${totalMatches} total matches`;
}

/**
 * MODAL & PDF REPORT
 */
function openModal(data, allMatches = []) {
    const mainImgSrc = getLogoUrl(data.id);
    const wrap = document.getElementById('modalImageWrap');
    wrap.innerHTML = `<img src="${mainImgSrc}" style="width:100%;height:100%;object-fit:contain;">`;

    document.getElementById("modalCompanyName").textContent = data.label || "N/A";
    document.getElementById("modalImageSim").textContent = `${data.imgSim}%`;
    document.getElementById("modalTextSim").textContent = `${data.textSim}%`;
    document.getElementById("modalTrademarkNum").textContent = data.serial || "N/A";
    document.getElementById("modalClass").textContent = data.modalClass || "N/A";
    document.getElementById("modalAgent").textContent = data.modalAgent || "N/A";
    document.getElementById("modalDescription").textContent = data.description || "N/A";

    const matchesList = document.getElementById("modalMatchesList");
    matchesList.innerHTML = "";

    const others = allMatches.filter(m => m.id !== data.id).slice(0, 3);
    modalTopMatches = others;
    others.forEach(m => {
        const item = document.createElement('div');
        item.className = 'modal-match-row';
        item.style = "display: flex; align-items: center; gap: 15px; padding: 12px; border-bottom: 1px solid #eee; cursor: pointer;";
        const subImgSrc = getLogoUrl(m.id);
        item.innerHTML = `
            <img src="${subImgSrc}" style="width: 45px; height: 45px; object-fit: contain;">
            <div style="flex: 1;">
                <div style="font-weight: 600;">${m.label}</div>
                <div style="font-size: 0.8rem;">${m.serial || ''}</div>
            </div>
            <div style="font-weight: bold; color: #4f46e5;">${m.totalSim}%</div>`;
        
        item.onclick = () => openModal(m, allMatches);
        matchesList.appendChild(item);
    });

    document.getElementById('detailModal').classList.add('show');
}

function closeModal() {
    document.getElementById('detailModal').classList.remove('show');
}

document.getElementById("modalDownload").onclick = async function() {
    const logoSrc = document.querySelector("#modalImageWrap img").src;
    const trademarkId = logoSrc.split('/').pop();

    const reportData = {
        id: trademarkId,
        isClientCompare: selectedCompare === 'clientRight',
        label: document.getElementById("modalCompanyName").textContent,
        imgSim: document.getElementById("modalImageSim").textContent.replace('%', ''),
        textSim: document.getElementById("modalTextSim").textContent.replace('%', ''),
        serial: document.getElementById("modalTrademarkNum").textContent,
        modalClass: document.getElementById("modalClass").textContent,
        modalAgent: document.getElementById("modalAgent").textContent,
        description: document.getElementById("modalDescription").textContent,
        topMatches: modalTopMatches
    };

    showPopup("📄 Generating PDF report...");

    try {
        const response = await fetch('/api/generate_pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(reportData)
        });
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Report_${reportData.serial}.pdf`;
        a.click();
    } catch (err) {
        showPopup("❌ PDF failed", true);
    }
};

/**
 * RESET
 */
function resetCompare() {
    selectedSource = null;
    selectedCompare = null;
    uploadedFiles = [];
    
    document.querySelectorAll('.compare-page-checkbox').forEach(cb => cb.checked = false);
    document.querySelectorAll('.compare-page-item').forEach(el => el.classList.remove('selected', 'has-files'));
    
    renderUploadPreviews();
    document.getElementById('resultsSection').classList.remove('show');
    document.getElementById('compareBtn').disabled = true;
    document.getElementById('resetBtn').style.display = 'none';
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function showPopup(msg, isError = false) {
    const el = document.getElementById('comparePopup');
    el.textContent = msg;
    el.className = 'compare-page-popup show' + (isError ? ' error' : '');
    setTimeout(() => el.classList.remove('show'), 3000);
}