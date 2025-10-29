   const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');
    const searchBtn = document.getElementById('searchBtn');
    const resultsSection = document.getElementById('resultsSection');
    let uploadedFile = null;

    // Click to browse
    uploadArea.addEventListener('click', (e) => {
      if (!e.target.closest('.uploaded-image-preview')) {
        fileInput.click();
      }
    });

    // File input change
    fileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        handleFileUpload(file);
      }
    });

    // Drag and drop
    uploadArea.addEventListener('dragover', (e) => {
      e.preventDefault();
      uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
      uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadArea.classList.remove('dragover');
      const file = e.dataTransfer.files[0];
      if (file && file.type.startsWith('image/')) {
        handleFileUpload(file);
      }
    });

    function handleFileUpload(file) {
        uploadedFile = file;
        const reader = new FileReader();
        reader.onload = (e) => {
            uploadArea.innerHTML = `
            <div class="uploaded-image-wrapper">
                <img src="${e.target.result}" class="uploaded-image-preview" alt="Uploaded trademark">
                <button class="delete-upload-btn" title="Remove Image">
                <img src="file-icons/delete.png" alt="Delete" class="delete-icon">
                </button>
            </div>
            <div class="uploaded-file-name">${file.name}</div>
            `;

            // Add delete functionality
            const deleteBtn = uploadArea.querySelector('.delete-upload-btn');
            deleteBtn.addEventListener('click', (event) => {
            event.stopPropagation();
            uploadedFile = null;
            uploadArea.innerHTML = `
                <div class="search-upload-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="17 8 12 3 7 8" />
                    <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                </div>
                <div class="search-upload-text">
                Drag & drop a file or <span class="browse">Browse</span>
                </div>
                <div class="search-upload-formats">
                Supported formats: JPEG, JPG, PNG, GIF
                </div>
                <input type="file" id="fileInput" class="search-file-input" accept="image/*">
            `;
            // Rebind file input listener
            const newFileInput = uploadArea.querySelector('#fileInput');
            newFileInput.addEventListener('change', (e) => {
                const newFile = e.target.files[0];
                if (newFile) handleFileUpload(newFile);
            });
            });
        };
        reader.readAsDataURL(file);
    }

    searchBtn.addEventListener('click', () => {
      const words = document.getElementById('wordsInput').value;
      const classValue = document.getElementById('classInput').value;
      
      if (uploadedFile || words || classValue) {
        resultsSection.classList.add('show');
        setTimeout(() => {
          resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 300);
      }
    });