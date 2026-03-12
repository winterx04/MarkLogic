// =========================================================================
// utils.js - Shared helper functions for the entire application
// =========================================================================

// --- POPUP NOTIFICATION ---
let popupTimeout = null;
function showPopup(message, type = 'success') {
    const popup = document.getElementById('popup');
    if (!popup) return;
    clearTimeout(popupTimeout);
    popup.textContent = message;
    popup.className = `admin-popup-notification ${type} show`;
    popupTimeout = setTimeout(() => {
        popup.classList.remove('show');
    }, 3000);
}

// --- CONFIRMATION MODAL ---
function showConfirmModal(message, onConfirm) {
    const confirmModal = document.getElementById('confirmModal');
    if (!confirmModal) {
        // Fallback to browser's confirm if the modal isn't on the page
        if (window.confirm(message)) {
            if (onConfirm) onConfirm();
        }
        return;
    }
    const confirmMessageEl = document.getElementById('confirmMessage');
    const confirmActionBtn = document.getElementById('confirmActionBtn');
    const confirmCancelBtn = document.getElementById('confirmCancelBtn');

    confirmMessageEl.textContent = message;
    confirmModal.style.display = 'flex';

    // Re-clone the button to remove old event listeners
    const newConfirmBtn = confirmActionBtn.cloneNode(true);
    confirmActionBtn.parentNode.replaceChild(newConfirmBtn, confirmActionBtn);
    
    newConfirmBtn.addEventListener('click', () => {
        confirmModal.style.display = 'none';
        if (onConfirm) onConfirm();
    });

    confirmCancelBtn.addEventListener('click', () => {
        confirmModal.style.display = 'none';
    }, { once: true });
}