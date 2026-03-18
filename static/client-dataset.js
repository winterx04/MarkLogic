/**
 * client-dataset.js
 * Complete logic for Tab Switching, AI Upload Streaming, and Manage Table Search
 */

document.addEventListener('DOMContentLoaded', () => {
    console.log("🚀 Client Dataset Logic Initialized");

    // ==========================================
    // 1. SELECTORS
    // ==========================================
    const tabBtns = document.querySelectorAll(".dataset-tab-btn");
    const tabPanels = document.querySelectorAll(".dataset-tab-panel");
    
    const uploadArea = document.getElementById("uploadArea");
    const fileInput = document.getElementById("fileInput");
    const uploadBtn = document.getElementById("uploadBtn");
    
    const progressContainer = document.getElementById("progressContainer");
    const progressBar = document.getElementById("progressBar");
    const progressPercent = document.getElementById("progressPercent");
    const progressText = document.getElementById("progressText");

    const tbody = document.getElementById("clientTableBody");
    const searchBtn = document.getElementById("btnSearchClient");
    const searchInput = document.getElementById("searchClientName");
    const resetBtn = document.getElementById("resetClientSearch");

    let selectedFiles = [];




    // ==========================================
    // 2. TAB SWITCHING (Hardened for Visual Fix)
    // ==========================================

    function showPlaceholderMessage() {
      const tbody = document.getElementById("fileTableBody");
      if (tbody) {
          tbody.innerHTML = `
              <tr>
                  <td colspan="4" style="text-align:center; padding:40px; color:rgba(255,255,255,0.5);">
                      <div style="font-size: 2rem; margin-bottom: 10px;">🔍</div>
                      Enter an Applicant Name or Description above to search the dataset.
                  </td>
              </tr>
          `;
      }
    }

    tabBtns.forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            const tabName = btn.dataset.tab;
            console.log(`Attempting to switch to: ${tabName}`);

            // Update Button Visuals
            tabBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            // Update Panel Visuals (Force Display)
            tabPanels.forEach(p => {
                const isTarget = p.id === `${tabName}-panel`;
                p.classList.toggle("active", isTarget);
                p.style.display = isTarget ? "block" : "none"; // Explicit override
            });

            if (tabName === 'manage') {
                //showPlaceholderMessage();   // Show placeholder until results load OR Change this to loadClientTable("") to show all records immediately
                loadClientTable("");        // Load all records when Manage tab is clicked
                setTimeout(attachSearchListener, 100);
            }
        });
    });

    // ==========================================
    // 3. FILE UPLOAD & PREVIEW
    // ==========================================
    if (uploadArea) {
        uploadArea.addEventListener("click", () => fileInput.click());
        uploadArea.addEventListener("dragover", (e) => {
            e.preventDefault();
            uploadArea.classList.add("dragover");
        });
        uploadArea.addEventListener("dragleave", () => uploadArea.classList.remove("dragover"));
        uploadArea.addEventListener("drop", (e) => {
            e.preventDefault();
            uploadArea.classList.remove("dragover");
            if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
        });
    }

    if (fileInput) {
        fileInput.addEventListener("change", (e) => handleFiles(e.target.files));
    }

    function handleFiles(files) {
        selectedFiles = [files[0]];
        console.log("File Selected:", selectedFiles[0].name);
        const dropText = document.getElementById("dropText");
        if (dropText) dropText.innerHTML = `Selected: <strong>${selectedFiles[0].name}</strong>`;
        uploadBtn.disabled = false;
    }

    // ==========================================
    // 4. UPLOAD ACTION (STREAMING)
    // ==========================================
    uploadBtn.addEventListener("click", async () => {
        const fileName = document.getElementById("fileName").value.trim();
        const fileDate = document.getElementById("fileDate").value;

        if (!selectedFiles.length || !fileDate) {
            return showPopup("Please select a file and a date.", true);
        }

        const formData = new FormData();
        formData.append('file', selectedFiles[0]);
        formData.append('user_file_name', fileName || selectedFiles[0].name);
        formData.append('user_date', fileDate);

        progressContainer.style.display = "block";
        uploadBtn.disabled = true;
        uploadBtn.innerText = "⏳ Initializing AI...";

        try {
            const response = await fetch('/upload-client-dataset', {
                method: 'POST',
                body: formData
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let leftover = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const lines = (leftover + chunk).split('\n');
                leftover = lines.pop();

                for (const line of lines) {
                    if (!line.trim()) continue;
                    const data = JSON.parse(line);

                    if (data.status === "extracting" || data.status === "inserting") {
                        const pct = data.percentage || 0;
                        progressBar.style.width = `${pct}%`;
                        progressPercent.innerText = `${pct}%`;
                        progressText.innerText = data.status === "extracting" 
                            ? `AI Scanning Page ${data.current_page || ''}...` 
                            : `Saving Record...`;
                    } 
                    else if (data.status === "complete") {
                        showPopup("✅ " + data.message);
                        setTimeout(() => location.reload(), 2000);
                    }
                    else if (data.status === "error") {
                        showPopup("❌ " + data.message, true);
                    }
                }
            }
        } catch (err) {
            console.error(err);
            showPopup("❌ Upload failed.", true);
        } finally {
            uploadBtn.disabled = false;
        }
    });

    // ==========================================
    // 5. MANAGE TAB SEARCH & TABLE
    // ==========================================
    async function loadClientTable(query = "") {
        if (!tbody) {
            console.error("❌ Table Body 'clientTableBody' NOT FOUND in HTML!");
            return;
        }

        console.log(`📡 Fetching Client Data for: "${query}"`);
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:20px;">Searching...</td></tr>';

        try {
            const res = await fetch(`/api/client-trademarks?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            console.log("📦 Results received:", data.length);

            tbody.innerHTML = "";
            if (data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:20px;">No records found.</td></tr>';
                return;
            }

            data.forEach(item => {
                const row = document.createElement("tr");
                row.innerHTML = `
                    <td class="table-checkbox-col">
                        <input type="checkbox" class="manage-checkbox" data-id="${item.id}">
                    </td>
                    <td>${item.applicant_name || 'N/A'}</td>
                    <td>${item.description || 'N/A'}</td>
                    <td>${item.upload_date || 'N/A'}</td>
                `;
                tbody.appendChild(row);
            });
        } catch (e) {
            console.error("Fetch Error:", e);
            tbody.innerHTML = '<tr><td colspan="4" style="color:red; text-align:center;">Error loading results.</td></tr>';
        }
    }

    function attachSearchListener() {
        const btn = document.getElementById("btnSearchClient");
        if (btn) {
            // Remove old listener
            const newBtn = btn.cloneNode(true);
            btn.parentNode.replaceChild(newBtn, btn);
            
            newBtn.addEventListener("click", () => {
                console.log("🔍 Search Clicked");
                const term = document.getElementById("searchClientName").value.trim();
                loadClientTable(term);
            });
            console.log("✅ Search Listener Attached");
        }
    }

    // RESET SEARCH FUNCTIONALITY
    if (resetBtn) {
        resetBtn.addEventListener("click", () => {
            console.log("🔄 Resetting search filters...");
            
            // 1. Clear the text input
            if (searchInput) searchInput.value = "";
            
            // 2. Reload the full table with all data (empty query) 
            loadClientTable(""); 

            //showPlaceholderMessage(); // Show placeholder until results load (Basically no results when reset)
            
            // 3. Show feedback
            showPopup("Search cleared.");
        });
        console.log("✅ Reset Listener Attached to resetClientSearch");
    } else {
        console.warn("⚠️ Reset button 'resetClientSearch' not found in HTML.");
    }
    // ==========================================
    // 6. HELPERS
    // ==========================================
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

    // Initial load
    attachSearchListener();
});