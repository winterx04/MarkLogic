// =========================================================================
// user_management.js - FINAL SCRIPT for User Management Page
// This file handles the table, modals, and API calls for this page only.
// It DEPENDS on utils.js for showPopup and showConfirmModal.
// =========================================================================
document.addEventListener('DOMContentLoaded', () => {
    // --- Get all necessary static DOM elements ---
    const usersTableBody = document.getElementById('usersTableBody');
    const openAddUserBtn = document.getElementById('openAddUserBtn');
    const addUserModal = document.getElementById('addUserModal');
    const cancelAddUserBtn = document.getElementById('cancelAddUserBtn');
    const addUserForm = document.getElementById('addUserForm');
    const modalTitle = document.getElementById('addUserTitle');
    const modalSubmitBtn = addUserForm ? addUserForm.querySelector('button[type="submit"]') : null;
    const modalRoleDropdown = document.getElementById('modalRoleDropdown');

    // --- Guard Clause: Stop if we're not on the user management page ---
    if (!usersTableBody) {
        return; 
    }

    // =====================================================================
    // PAGE-SPECIFIC UI HELPER FUNCTIONS
    // =====================================================================
    function openAddUserModal() {
        if (addUserModal) {
            addUserModal.classList.add('show');
            // Safely set default role in modal to "User" for new users
            const userOption = modalRoleDropdown.querySelector('.admin-role-option[data-value="User"]');
            if (userOption) selectRoleInModal(userOption);
        }
    }

    function closeAddUserModal() {
        if (addUserModal) {
            addUserModal.classList.remove('show');
            addUserForm.reset();
            // Always reset modal back to "Add" mode when closing
            modalTitle.textContent = 'Add New User';
            modalSubmitBtn.textContent = 'Add User';
            delete addUserForm.dataset.editId;
        }
    }

    function toggleRoleDropdown(element) {
        const dropdown = element.closest('.admin-role-dropdown');
        if (!dropdown) return;
        // Close all other dropdowns first
        document.querySelectorAll('.admin-role-dropdown.show').forEach(d => {
            if (d !== dropdown) d.classList.remove('show');
        });
        dropdown.classList.toggle('show');
    }

    function selectRoleInModal(option) {
        const dropdown = option.closest('.admin-role-dropdown');
        if (!dropdown) return;
        dropdown.querySelectorAll('.admin-role-option').forEach(opt => opt.classList.remove('selected'));
        option.classList.add('selected');
        dropdown.querySelector('.admin-role-select span').textContent = option.dataset.value;
    }

    // =====================================================================
    // ACTION HANDLERS (These make the API calls to Flask)
    // =====================================================================

    // const handleFormSubmit = (event) => {
    //     event.preventDefault();
    //     const name = document.getElementById('newUserName').value.trim();
    //     const email = document.getElementById('newUserEmail').value.trim();
    //     const role = document.querySelector('#modalRoleDropdown .admin-role-option.selected')?.dataset.value || 'User';
    //     const editId = addUserForm.dataset.editId;

    //     if (!name || !email) {
    //         showPopup('Name and email are required.', 'error'); // Uses showPopup from utils.js
    //         return;
    //     }

    //     if (editId) {
    //         // --- EDIT LOGIC ---
    //         fetch('/api/users/edit', {
    //             method: 'POST',
    //             headers: { 'Content-Type': 'application/json' },
    //             body: JSON.stringify({ id: editId, name, email })
    //         })
    //         .then(res => res.json()).then(data => {
    //             showPopup(data.message, data.success ? 'success' : 'error');
    //             if (data.success) {
    //                 closeAddUserModal();
    //                 window.location.reload();
    //             }
    //         });
    //     } else {
    //         // --- ADD LOGIC (invitation system) ---
    //         fetch('/api/users/add', {
    //             method: 'POST',
    //             headers: { 'Content-Type': 'application/json' },
    //             body: JSON.stringify({ name, email, role })
    //         })
    //         .then(res => res.json()).then(data => {
    //             showPopup(data.message, data.success ? 'success' : 'error');
    //             if (data.success) {
    //                 closeAddUserModal();
    //                 window.location.reload();
    //             }
    //         });
    //     }
    // };

    // =====================================================================
    // PASSWORD RESET LOGIC (ADMIN RESETTING A USER'S PASSWORD) FOR ITERATION 2
    // =====================================================================

    const handleFormSubmit = (event) => {
        event.preventDefault();
        const name = document.getElementById('newUserName').value.trim();
        const email = document.getElementById('newUserEmail').value.trim();
        // This is the new password field from the edit modal
        const newPassword = document.getElementById('editUserPassword').value.trim();
        // Get the role, only needed for adding a new user
        const role = document.querySelector('#modalRoleDropdown .admin-role-option.selected')?.dataset.value || 'User';
        const editId = addUserForm.dataset.editId;

        if (!name || !email) {
            showPopup('Name and email are required.', 'error');
            return;
        }

        if (editId) {
            // --- EDIT LOGIC ---

            // Step 1: Update the user's name and email.
            fetch('/api/users/edit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: editId, name, email })
            })
            .then(res => res.json())
            .then(data => {
                // Show the result of the name/email update
                showPopup(data.message, data.success ? 'success' : 'error');

                // Step 2: Check if a new password was entered.
                if (data.success && newPassword) {
                    // If the name/email update was successful AND there's a new password,
                    // make the second API call to reset the password.
                    fetch('/api/users/admin_reset_password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id: editId, password: newPassword })
                    })
                    .then(res => res.json())
                    .then(passwordData => {
                        // Show the result of the password reset action
                        showPopup(passwordData.message, passwordData.success ? 'success' : 'error');
                    });
                }

                // Step 3: Close the modal and reload the page to see all changes.
                if (data.success) {
                    closeAddUserModal();
                    // Use a short delay to allow the user to read the popup messages.
                    setTimeout(() => {
                        window.location.reload();
                    }, 1500); // 1.5 second delay
                }
            })
            .catch(error => {
                console.error('Error updating user:', error);
                showPopup('A network error occurred.', 'error');
            });

        } else {
            // --- ADD LOGIC (This remains the same for the email invitation system) ---
            fetch('/api/users/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, email, role })
            })
            .then(res => res.json())
            .then(data => {
                showPopup(data.message, data.success ? 'success' : 'error');
                if (data.success) {
                    closeAddUserModal();
                    setTimeout(() => {
                        window.location.reload();
                    }, 2000); // 2 second delay
                }
            });
        }
    };

    const handleDelete = (button) => {
        const row = button.closest('tr');
        const userId = row.dataset.userId;
        showConfirmModal('Are you sure you want to delete this user?', () => { // Uses showConfirmModal from utils.js
            fetch(`/api/users/delete/${userId}`, { method: 'DELETE' })
            .then(res => res.json()).then(data => {
                showPopup(data.message, data.success ? 'success' : 'error');
                if (data.success) row.remove();
            });
        });
    };

    const handleEdit = (button) => {
        const row = button.closest('tr');
        const userId = row.dataset.userId;
        const currentName = row.querySelector('.user-name').textContent;
        const currentEmail = row.querySelector('.user-email').textContent;
        
        // Populate modal with existing data
        document.getElementById('newUserName').value = currentName;
        document.getElementById('newUserEmail').value = currentEmail;
        
        // --- THIS IS THE FIX ---
        // Get the containers for the fields we want to toggle
        const passwordGroup = document.getElementById('editPasswordGroup');
        const roleGroup = modalRoleDropdown.closest('.form-group');

        // In EDIT mode, SHOW the password field and HIDE the role field.
        if (passwordGroup) passwordGroup.style.display = 'block';
        if (roleGroup) roleGroup.style.display = 'none';
        // --- END OF FIX ---

        // Switch modal to "Edit Mode"
        modalTitle.textContent = 'Edit User';
        modalSubmitBtn.textContent = 'Update User';
        addUserForm.dataset.editId = userId;
        
        openAddUserModal();
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
        .then(res => res.json()).then(data => {
            showPopup(data.message, data.success ? 'success' : 'error');
            if (data.success) {
                dropdown.querySelector('.admin-role-select span').textContent = newRole;
                dropdown.querySelectorAll('.admin-role-option').forEach(opt => {
                    opt.classList.toggle('selected', opt.dataset.value === newRole);
                });
            } else {
                window.location.reload();
            }
        });
    };

    // =====================================================================
    // BINDING ALL EVENT LISTENERS
    // =====================================================================
    
    usersTableBody.addEventListener('click', (event) => {
        const target = event.target;
        
        const deleteButton = target.closest('.admin-delete-btn');
        if (deleteButton) { handleDelete(deleteButton); return; }

        const editButton = target.closest('.admin-edit-btn');
        if (editButton) { handleEdit(editButton); return; }
        
        const roleOption = target.closest('.admin-role-option');
        if (roleOption) { handleRoleChange(roleOption); }
        
        const roleSelect = target.closest('.admin-role-select');
        if (roleSelect) { toggleRoleDropdown(roleSelect); }
    });

    openAddUserBtn.addEventListener('click', () => {
        // Get the containers for the fields we want to toggle
        const passwordGroup = document.getElementById('editPasswordGroup');
        const roleGroup = modalRoleDropdown.closest('.form-group');

        // In ADD mode, HIDE the password field and SHOW the role field.
        if (passwordGroup) passwordGroup.style.display = 'none';
        if (roleGroup) roleGroup.style.display = 'block';
        // --- END OF FIX ---

        openAddUserModal();
    });

    cancelAddUserBtn.addEventListener('click', closeAddUserModal);
    addUserForm.addEventListener('submit', handleFormSubmit);
    addUserModal.addEventListener('click', (e) => {
        if(e.target === addUserModal) closeAddUserModal();
        const roleSelect = e.target.closest('.admin-role-select');
        if (roleSelect) toggleRoleDropdown(roleSelect);
        const roleOption = e.target.closest('.admin-role-option');
        if (roleOption) selectRoleInModal(roleOption);
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.admin-role-dropdown')) {
            document.querySelectorAll('.admin-role-dropdown.show').forEach(d => d.classList.remove('show'));
        }
    });
});
