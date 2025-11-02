// --- Rerender Table from Server Data ---
const fetchAndRenderUsers = async () => {
    const response = await fetch('/admin'); // Re-fetch the admin page content
    const html = await response.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const newTbody = doc.querySelector('#usersTableBody');
    $q('#usersTableBody').innerHTML = newTbody.innerHTML;
    bindEventListeners(); // Re-attach listeners to new elements
};

// --- Event Handlers ---
const handleAddUser = (event) => {
    event.preventDefault();
    const name = $q('#newUserName').value.trim();
    const email = $q('#newUserEmail').value.trim();
    const password = $q('#newUserPassword').value.trim();
    const role = $q('#modalRoleDropdown .admin-role-option.selected')?.dataset.value || 'User';

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
            fetchAndRenderUsers();
        }
    });
};

const handleDeleteUser = (event) => {
    const row = event.target.closest('tr');
    const userId = row.dataset.userId;
    showConfirmModal('Are you sure you want to delete this user?', () => {
        fetch(`/api/users/delete/${userId}`, { method: 'DELETE' })
        .then(res => res.json())
        .then(data => {
            showPopup(data.message, data.success ? 'success' : 'error');
            if (data.success) {
                row.remove();
            }
        });
    });
};

const handleRoleChange = (event) => {
    const option = event.target.closest('.admin-role-option');
    const dropdown = event.target.closest('.admin-role-dropdown');
    if (!option || !dropdown) return;

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
        if(data.success) {
             dropdown.querySelector('.admin-role-select span').textContent = newRole;
        }
    });
};

// --- Main Function to Bind All Listeners ---
const bindEventListeners = () => {
    // Add User Modal Logic
    $q('#openAddUserBtn')?.addEventListener('click', openAddUserModal);
    $q('#cancelAddUserBtn')?.addEventListener('click', closeAddUserModal);
    $q('#addUserForm')?.addEventListener('submit', handleAddUser);

    // Logout
    $q('#logoutItem')?.addEventListener('click', () => {
        showConfirmModal('Are you sure you want to log out?', () => {
            window.location.href = '/logout';
        });
    });

    // Table Actions (Delete and Role Change)
    document.querySelectorAll('.admin-delete-btn').forEach(btn => btn.addEventListener('click', handleDeleteUser));
    document.querySelectorAll('.admin-role-option').forEach(opt => opt.addEventListener('click', handleRoleChange));
    // Add other listeners from your original script (dropdown toggles, etc.)
};

// --- Initial Setup ---
bindEventListeners();
// Copy all other UI functions from your original script here (open/close modals, toggles, etc.)
   
const datasetMenuCard = document.getElementById('datasetMenuCard');
const datasetModal = document.getElementById('datasetModal');
const modalCancel = document.getElementById('modalCancel');

datasetMenuCard.addEventListener('click', (e) => {
    e.preventDefault();
    datasetModal.classList.add('show');
});

modalCancel.addEventListener('click', () => {
    datasetModal.classList.remove('show');
});

datasetModal.addEventListener('click', (e) => {
    if (e.target === datasetModal) {
        datasetModal.classList.remove('show');
    }
});
