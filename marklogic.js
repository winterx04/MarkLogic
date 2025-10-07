document.getElementById("signinForm").addEventListener("submit", function(e) {
    e.preventDefault(); // stop normal form submission

    let email = document.getElementById("email").value.trim();
    let password = document.getElementById("password").value.trim();
    let valid = true;

    // reset error messages
    document.getElementById("emailError").textContent = "";
    document.getElementById("passwordError").textContent = "";

    // email validation
    if (!email) {
        document.getElementById("emailError").textContent = "Email is required.";
        valid = false;
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        document.getElementById("emailError").textContent = "Enter a valid email address.";
        valid = false;
    }

    // password validation
    if (!password) {
        document.getElementById("passwordError").textContent = "Password is required.";
        valid = false;
    } else if (password.length < 6) {
        document.getElementById("passwordError").textContent = "Password must be at least 6 characters.";
        valid = false;
    }

    // if valid → redirect
    if (valid) {
        window.location.href = "menu.html";
    }
});

// Tab switching
const tabBtns = document.querySelectorAll('.dataset-tab-btn');
const tabPanels = document.querySelectorAll('.dataset-tab-panel');

tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
const tabName = btn.dataset.tab;

// Remove active class from all tabs and panels
tabBtns.forEach(b => b.classList.remove('active'));
tabPanels.forEach(p => p.classList.remove('active'));

// Add active class to clicked tab and corresponding panel
btn.classList.add('active');
document.getElementById(`${tabName}-panel`).classList.add('active');
    });
});

// File upload functionality
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
let selectedFiles = [];

// Click to browse
uploadArea.addEventListener('click', () => {
    fileInput.click();
});

// File selection
fileInput.addEventListener('change', (e) => {
    selectedFiles = Array.from(e.target.files);
    updateUploadButton();
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
    selectedFiles = Array.from(e.dataTransfer.files);
    updateUploadButton();
});

function updateUploadButton() {
    if (selectedFiles.length > 0) {
        uploadBtn.disabled = false;
        uploadBtn.textContent = `Upload ${selectedFiles.length} File${selectedFiles.length > 1 ? 's' : ''}`;
    } else {
        uploadBtn.disabled = true;
        uploadBtn.textContent = 'Upload Files';
    }
}

// Upload button click
uploadBtn.addEventListener('click', () => {
    if (selectedFiles.length > 0) {
alert(`Uploading ${selectedFiles.length} file(s)...`);
// Add your upload logic here
    }
});