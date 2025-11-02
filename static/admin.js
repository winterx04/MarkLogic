// =========================================================================
// admin.js - COMPLETE SCRIPT FOR USER MANAGEMENT PAGE
// This file ONLY manages the user table, add user modal, and related actions.
// The shared user icon/logout logic is in 'logout.js'.
// =========================================================================
document.addEventListener('DOMContentLoaded', () => {

    // --- Get all necessary static DOM elements ---
    const usersTableBody = document.getElementById('usersTableBody');
    const openAddUserBtn = document.getElementById('openAddUserBtn');
    const addUserModal = document.getElementById('addUserModal');
    const cancelAddUserBtn = document.getElementById('cancelAddUserBtn');
    const addUserForm = document.getElementById('addUserForm');
    
    // Check if we are on the correct page before running any code
    if (!usersTableBody) {
        // If there's no user table, don't run any of this page-specific code.
        return; 
    }

    // =====================================================================
    // UI HELPER FUNCTIONS (These must be defined first)
    // =====================================================================
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

    const confirmModal = document.getElementById('confirmModal');
    function showConfirmModal(message, onConfirm) {
        if (!confirmModal) return;
        const confirmMessageEl = document.getElementById('confirmMessage');
        const confirmActionBtn = document.getElementById('confirmActionBtn');
        const confirmCancelBtn = document.getElementById('confirmCancelBtn');

        confirmMessageEl.textContent = message;
        confirmModal.style.display = 'flex';

        // Re-clone the button to remove old event listeners, which is a robust way to handle this
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

    const openAddUserModal = () => {
        if (addUserModal) {
            addUserModal.classList.add('show');
            // Safely set default role in modal
            const userOption = addUserModal.querySelector('.admin-role-option[data-value="User"]');
            if (userOption) selectRoleInModal(userOption);
        }
    };
    const closeAddUserModal = () => {
        if (addUserModal) {
            addUserModal.classList.remove('show');
            addUserForm.reset();
        }
    };

    const toggleRoleDropdown = (element) => {
        const dropdown = element.closest('.admin-role-dropdown');
        if (!dropdown) return;
        // Close all other dropdowns first
        document.querySelectorAll('.admin-role-dropdown.show').forEach(d => {
            if (d !== dropdown) d.classList.remove('show');
        });
        dropdown.classList.toggle('show');
    };

    const selectRoleInModal = (option) => {
        const dropdown = option.closest('.admin-role-dropdown');
        if (!dropdown) return;
        dropdown.querySelectorAll('.admin-role-option').forEach(opt => opt.classList.remove('selected'));
        option.classList.add('selected');
        dropdown.querySelector('.admin-role-select span').textContent = option.dataset.value;
    };

    // =====================================================================
    // ACTION HANDLERS (These make the API calls to Flask)
    // =====================================================================

    const handleDeleteUser = (button) => {
        const row = button.closest('tr');
        const userId = row.dataset.userId;
        showConfirmModal('Are you sure you want to delete this user?', () => {
            fetch(`/api/users/delete/${userId}`, { method: 'DELETE' })
            .then(res => res.json())
            .then(data => {
                showPopup(data.message, data.success ? 'success' : 'error');
                if (data.success) row.remove();
            });
        });
    };
    
    const handleRoleChange = (option) => {
        const dropdown = option.closest('.admin-role-dropdown');
        const userId = dropdown.dataset.userId;
        const newRole = option.dataset.value;
        fetch('/api/users/update_role', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, role: newRole })
        })
        .then(res => res.json())
        .then(data => {
            showPopup(data.message, data.success ? 'success' : 'error');
            if (data.success) {
                dropdown.querySelector('.admin-role-select span').textContent = newRole;
                dropdown.querySelectorAll('.admin-role-option').forEach(opt => {
                    opt.classList.toggle('selected', opt.dataset.value === newRole);
                });
            }
        });
    };

    const handleAddUser = (event) => {
        event.preventDefault();
        const name = document.getElementById('newUserName').value.trim();
        const email = document.getElementById('newUserEmail').value.trim();
        const password = document.getElementById('newUserPassword').value.trim();
        const role = document.querySelector('#modalRoleDropdown .admin-role-option.selected')?.dataset.value || 'User';
        fetch('/api/users/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, password, role })
        })
        .then(res => res.json())
        .then(data => {
            showPopup(data.message, data.success ? 'success' : 'error');
            if (data.success) {
                closeAddUserModal();
                window.location.reload();
            }
        });
    };

    // =====================================================================
    // BINDING ALL EVENT LISTENERS
    // =====================================================================

    // --- Main table actions (using event delegation) ---
    usersTableBody.addEventListener('click', (event) => {
        const target = event.target;
        const deleteButton = target.closest('.admin-delete-btn');
        if (deleteButton) {
            handleDeleteUser(deleteButton);
            return;
        }
        const roleOption = target.closest('.admin-role-option');
        if (roleOption) {
            handleRoleChange(roleOption);
        }
        const roleSelect = target.closest('.admin-role-select');
        if (roleSelect) {
            toggleRoleDropdown(roleSelect);
        }
    });

    // --- Add User Modal (static elements) ---
    openAddUserBtn.addEventListener('click', openAddUserModal);
    cancelAddUserBtn.addEventListener('click', closeAddUserModal);
    addUserForm.addEventListener('submit', handleAddUser);
    addUserModal.addEventListener('click', (e) => {
        if(e.target === addUserModal) closeAddUserModal(); // Close if clicking on overlay
        const roleSelect = e.target.closest('.admin-role-select');
        if (roleSelect) toggleRoleDropdown(roleSelect);
        const roleOption = e.target.closest('.admin-role-option');
        if (roleOption) selectRoleInModal(roleOption);
    });

    // --- Global listener to close dropdowns ---
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.admin-role-dropdown')) {
            document.querySelectorAll('.admin-role-dropdown.show').forEach(d => d.classList.remove('show'));
        }
    });
});