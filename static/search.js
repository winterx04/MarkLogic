// This is the complete, merged content for your static/search.js file
document.addEventListener('DOMContentLoaded', () => {
    // --- All your variables ---
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');
    const searchBtn = document.getElementById('searchBtn');
    const resultsSection = document.getElementById('resultsSection');
    const resultsBody = document.getElementById('resultsBody');
    const wordsInput = document.getElementById('wordsInput');
    const classInput = document.getElementById('classInput');
    let uploadedFile = null;

    // =========================================================================
    // YOUR EXISTING FILE UPLOAD & DRAG-AND-DROP LOGIC (UNCHANGED)
    // =========================================================================
    uploadArea.addEventListener('click', (e) => {
        if (!e.target.closest('.uploaded-image-preview')) {
            fileInput.click();
        }
    });

    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) handleFileUpload(file);
    });

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
                <img src="{{ url_for('static', filename='file-icons/delete.png') }}" alt="Delete" class="delete-icon">
                </button>
            </div>
            <div class="uploaded-file-name">${file.name}</div>
            `;
            const deleteBtn = uploadArea.querySelector('.delete-upload-btn');
            deleteBtn.addEventListener('click', (event) => {
                event.stopPropagation();
                uploadedFile = null;
                // Reset UI to original state
                const originalUploadAreaHTML = `
                    <div class="search-upload-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg>
                    </div>
                    <div class="search-upload-text">Drag & drop a file or <span class="browse">Browse</span></div>
                    <div class="search-upload-formats">Supported formats: JPEG, JPG, PNG, GIF</div>
                    <input type="file" id="fileInput" class="search-file-input" accept="image/*">`;
                uploadArea.innerHTML = originalUploadAreaHTML;
                // Re-assign the fileInput variable and re-attach the listener
                const newFileInput = document.getElementById('fileInput');
                newFileInput.addEventListener('change', (e) => {
                    const newFile = e.target.files[0];
                    if (newFile) handleFileUpload(newFile);
                });
            });
        };
        reader.readAsDataURL(file);
    }

    // =========================================================================
    // NEW DYNAMIC TABLE UPDATE FUNCTION
    // =========================================================================
    const updateTable = (trademarks) => {
        resultsBody.innerHTML = '';
        if (trademarks.length === 0) {
            resultsBody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 20px;">No results found.</td></tr>';
            return;
        }
        trademarks.forEach(trademark => {
            const logoHtml = trademark.has_logo
                ? `<div class="trademark-image"><img src="/logo/${trademark.id}" alt="Trademark Logo"></div>`
                : `<div class="trademark-image no-logo"><span>No Logo</span></div>`;
            const rowHtml = `
                <tr>
                    <td class="trademark-cell">${logoHtml}</td>
                    <td>${trademark.class_indices || 'N/A'}</td>
                    <td class="id-cell">${trademark.serial_number || 'N/A'}</td>
                    <td>${trademark.applicant_name || 'N/A'}</td>
                    <td>${trademark.description || 'N/A'}</td>
                </tr>`;
            resultsBody.insertAdjacentHTML('beforeend', rowHtml);
        });
    };

    // =========================================================================
    // UPDATED SEARCH BUTTON LOGIC
    // =========================================================================
    // searchBtn.addEventListener('click', () => {
    //     const words = wordsInput.value.trim();
    //     const classValue = classInput.value.trim();

    //     // Check if there's anything to search for
    //     if (!uploadedFile && !words && !classValue) {
    //         alert('Please enter a search term or upload an image.');
    //         return;
    //     }
        
    //     // Show and scroll to results section immediately for better UX
    //     resultsSection.classList.add('show');
    //     setTimeout(() => {
    //       resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    //     }, 100);

    //     // Use FormData to send both text and file data
    //     const formData = new FormData();
    //     formData.append('words', words);
    //     formData.append('class_filter', classValue);
    //     if (uploadedFile) {
    //         formData.append('image', uploadedFile);
    //     }

    //     // Display a loading state in the table
    //     resultsBody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 20px;">Searching...</td></tr>';
        
    //     // Send the combined data to a new API endpoint
    //     // fetch('/api/combined_search', {
    //     fetch('/api/image_search', {
    //         method: 'POST',
    //         body: formData, // No 'Content-Type' header needed; browser sets it for FormData
    //     })
    //     .then(response => response.json())
    //     .then(data => {
    //         updateTable(data); // Update the table with the results
    //     })
    //     .catch(error => {
    //         console.error('Error during search:', error);
    //         resultsBody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 20px;">An error occurred. Please try again.</td></tr>';
    //     });
    // });

    searchBtn.addEventListener('click', () => {
    const words = wordsInput.value.trim();
    const classFilter = classInput.value.trim();

    // --- DECISION LOGIC ---

        // CASE 1: The user uploaded an image.
        if (uploadedFile) {
            // Use FormData to send the image and optional text filters.
            const formData = new FormData();
            formData.append('image', uploadedFile);
            formData.append('words', words);
            formData.append('class_filter', classFilter);
            
            // Show loading state and scroll
            resultsSection.classList.add('show');
            resultsBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Finding visually similar logos...</td></tr>';
            
            // Call the IMAGE search API
            fetch('/api/image_search', {
                method: 'POST',
                body: formData, // No Content-Type header needed for FormData
            })
            .then(response => response.json())
            .then(data => {
                updateTable(data);
            })
            .catch(error => {
                console.error('Image Search Error:', error);
                resultsBody.innerHTML = '<tr><td colspan="5">An error occurred during image search.</td></tr>';
            });
        }
        // CASE 2: No image, but the user entered text or a class.
        else if (words || classFilter) {
            // Show loading state and scroll
            resultsSection.classList.add('show');
            resultsBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Searching by text...</td></tr>';

            // Call the TEXT search API
            fetch('/api/text_search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json', // We are sending JSON now
                },
                body: JSON.stringify({
                    words: words,
                    class_filter: classFilter
                }),
            })
            .then(response => response.json())
            .then(data => {
                updateTable(data);
            })
            .catch(error => {
                console.error('Text Search Error:', error);
                resultsBody.innerHTML = '<tr><td colspan="5">An error occurred during text search.</td></tr>';
            });
        }
        // CASE 3: The user provided nothing.
        else {
            alert('Please enter a search term or upload an image.');
        }
    });
});