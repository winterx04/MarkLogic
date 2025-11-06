  // ==========================
  // User Data (In-Memory)
  // ==========================
  let users = [
    { name: 'Victoria Foo', email: 'victoria.foo@skrine.com', role: 'Admin' },
    { name: 'Xian Xin', email: 'xianxin@skrine.com', role: 'User' }
  ];

  // Helper - safe querySelector
  function $q(sel, ctx = document) { return ctx.querySelector(sel); }
  function $qa(sel, ctx = document) { return Array.from(ctx.querySelectorAll(sel)); }

  // ==========================
  // USER DROPDOWN (TOP-RIGHT)
  // ==========================
  const userIcon = document.getElementById('userIcon');
  const userDropdown = document.getElementById('userDropdown');

  function toggleUserDropdown() {
    if (!userDropdown) return;
    userDropdown.classList.toggle('show');
  }

  userIcon && userIcon.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleUserDropdown();
  });

  // Close dropdown when clicking outside
  document.addEventListener('click', function(e) {
    if (!userDropdown) return;
    if (!userDropdown.contains(e.target) && !userIcon.contains(e.target)) {
      userDropdown.classList.remove('show');
    }
  });

  // Logout (uses confirm modal)
  const logoutItem = document.getElementById('logoutItem');
  logoutItem && logoutItem.addEventListener('click', () => {
    showConfirmModal('Are you sure you want to log out?', () => {
      showPopup('Logging out...', 'success');
      setTimeout(() => window.location.href = 'signin.html', 600);
    });
  });

  // ==========================
  // ADD USER MODAL
  // ==========================
  const addUserModal = document.getElementById('addUserModal');
  const openAddUserBtn = document.getElementById('openAddUserBtn');
  const cancelAddUserBtn = document.getElementById('cancelAddUserBtn');
  const addUserForm = document.getElementById('addUserForm');
  const modalRoleDropdown = document.getElementById('modalRoleDropdown');

  function openAddUserModal() {
    if (!addUserModal) return;
    addUserModal.classList.add('show');
    addUserModal.setAttribute('aria-hidden', 'false');
    // default role in modal = User for safer UX
    setModalRole('User');
  }

  function closeAddUserModal() {
    if (!addUserModal) return;
    addUserModal.classList.remove('show');
    addUserModal.setAttribute('aria-hidden', 'true');
    // clear fields
    $q('#newUserName').value = '';
    $q('#newUserEmail').value = '';
    setModalRole('User');
    // reset modal title and button
    $q('#addUserTitle').textContent = 'Add New User';
    const submitBtn = addUserForm.querySelector('button[type="submit"]');
    submitBtn.textContent = 'Add User';
    delete addUserForm.dataset.editIndex;
  }

  function setModalRole(role) {
    const sel = modalRoleDropdown;
    if (!sel) return;
    sel.querySelector('.admin-role-select span').textContent = role;
    sel.querySelectorAll('.admin-role-option').forEach(opt => {
      opt.classList.toggle('selected', opt.textContent.trim() === role);
    });
  }

  // Close modal by clicking overlay
  addUserModal && addUserModal.addEventListener('click', function(e) {
    if (e.target === this) closeAddUserModal();
  });

  openAddUserBtn && openAddUserBtn.addEventListener('click', openAddUserModal);
  cancelAddUserBtn && cancelAddUserBtn.addEventListener('click', closeAddUserModal);

  // ==========================
  // USER MANAGEMENT
  // ==========================
  addUserForm && addUserForm.addEventListener('submit', function(event) {
    event.preventDefault();
    const name = $q('#newUserName').value.trim();
    const email = $q('#newUserEmail').value.trim();
    const role = modalRoleDropdown.querySelector('.admin-role-option.selected')?.textContent.trim() || 'User';

    if (!name || !email) {
      showPopup('Please fill in all fields.', 'error');
      return;
    }

    // Check if we're editing or adding
    const editIndex = addUserForm.dataset.editIndex;
    if (editIndex !== undefined && editIndex !== '') {
      // Edit existing user
      const index = parseInt(editIndex, 10);
      if (index >= 0 && index < users.length) {
        users[index] = { name, email, role };
        showPopup('User updated successfully!', 'success');
      }
      delete addUserForm.dataset.editIndex;
    } else {
      // Add new user
      users.push({ name, email, role });
      showPopup('User added successfully!', 'success');
    }

    renderUsers();
    closeAddUserModal();
  });

  function deleteUser(index) {
    showConfirmModal('Are you sure you want to delete this user?', () => {
      if (index >= 0 && index < users.length) {
        users.splice(index, 1);
        renderUsers();
        showPopup('User deleted successfully!', 'success');
      }
    });
  }

  function editUser(index) {
    if (index < 0 || index >= users.length) return;
    const user = users[index];
    
    // Populate modal with existing user data
    $q('#newUserName').value = user.name;
    $q('#newUserEmail').value = user.email;
    setModalRole(user.role);
    
    // Change modal title and button text
    $q('#addUserTitle').textContent = 'Edit User';
    const submitBtn = addUserForm.querySelector('button[type="submit"]');
    submitBtn.textContent = 'Update User';
    
    // Store the index being edited
    addUserForm.dataset.editIndex = index;
    
    openAddUserModal();
  }

  // ==========================
  // CUSTOM ROLE DROPDOWN (shared by table rows and modal)
  // ==========================
  function toggleRoleDropdown(element) {
    const dropdown = element.closest('.admin-role-dropdown');
    if (!dropdown) return;
    const allDropdowns = document.querySelectorAll('.admin-role-dropdown');

    // Close all others
    allDropdowns.forEach(d => {
      if (d !== dropdown) d.classList.remove('show');
    });

    // Toggle this one
    const willShow = !dropdown.classList.contains('show');
    dropdown.classList.toggle('show', willShow);
  }

  function selectRole(option, index, role) {
    const dropdown = option.closest('.admin-role-dropdown');
    if (!dropdown) return;

    // Update visual selection
    dropdown.querySelectorAll('.admin-role-option').forEach(opt => opt.classList.remove('selected'));
    option.classList.add('selected');
    dropdown.querySelector('.admin-role-select span').textContent = role;

    // If it's a user table dropdown (data-index >= 0)
    const datasetIndex = parseInt(dropdown.getAttribute('data-index'), 10);
    if (!Number.isNaN(datasetIndex) && datasetIndex >= 0 && users[datasetIndex]) {
      users[datasetIndex].role = role;
      renderUsers(); // re-render so indexes stay correct
      showPopup(`Role updated to ${role}`, 'success');
    }

    // Close dropdown
    dropdown.classList.remove('show');
  }

  // Close role dropdown when clicking outside
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.admin-role-dropdown')) {
      document.querySelectorAll('.admin-role-dropdown').forEach(d => d.classList.remove('show'));
    }
  });

  // ==========================
  // RENDER USERS TABLE
  // ==========================
  function renderUsers() {
    const tbody = document.getElementById('usersTableBody');
    tbody.innerHTML = '';

    users.forEach((user, index) => {
      const tr = document.createElement('tr');

      tr.innerHTML = `
        <td>${escapeHtml(user.name)}</td>
        <td>${escapeHtml(user.email)}</td>
        <td>
            <div class="admin-role-dropdown" data-index="${index}">
              <div class="admin-role-select" onclick="toggleRoleDropdown(this)">
                <span>${escapeHtml(user.role)}</span>
                <i class="fa-solid fa-chevron-down dropdown-icon"></i>
              </div>
              <div class="admin-role-options">
                <div class="admin-role-option ${user.role === 'Admin' ? 'selected' : ''}" onclick="selectRole(this, ${index}, 'Admin')">Admin</div>
                <div class="admin-role-option ${user.role === 'User' ? 'selected' : ''}" onclick="selectRole(this, ${index}, 'User')">User</div>
              </div>
            </div>
        </td>
        <td>
            <button class="admin-edit-btn" onclick="editUser(${index})">
              <i class="fa-solid fa-pen-to-square"></i>
              Edit
            </button>
            <button class="admin-delete-btn" onclick="deleteUser(${index})">
              <i class="fa-solid fa-trash"></i>
              Delete
            </button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  // Small helpers to avoid simple injection in values
  function escapeHtml(s) {
    if (typeof s !== 'string') return '';
    return s.replace(/[&<>"']/g, function (m) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m];
    });
  }
  function escapeAttr(s) {
    if (typeof s !== 'string') return '';
    return s.replace(/"/g, '&quot;');
  }

  // ==========================
  // POPUP NOTIFICATION
  // ==========================
  let popupTimeout = null;
  function showPopup(message, type = 'success') {
    const popup = document.getElementById('popup');
    clearTimeout(popupTimeout);
    popup.textContent = message;
    popup.className = `admin-popup-notification ${type} show`;

    popupTimeout = setTimeout(() => {
      popup.classList.remove('show');
      popup.className = 'admin-popup-notification';
    }, 3000);
  }

  // ==========================
  // CUSTOM CONFIRM MODAL
  // ==========================
  const confirmModal = document.getElementById('confirmModal');
  const confirmMessageEl = document.getElementById('confirmMessage');
  const confirmCancelBtn = document.getElementById('confirmCancelBtn');
  const confirmActionBtn = document.getElementById('confirmActionBtn');

  function showConfirmModal(message, onConfirm) {
    if (!confirmModal) return;
    confirmMessageEl.textContent = message;
    confirmModal.style.display = 'flex';

    // remove all previous listeners by cloning the confirm button
    const newConfirm = confirmActionBtn.cloneNode(true);
    confirmActionBtn.parentNode.replaceChild(newConfirm, confirmActionBtn);

    // also reset cancel
    const newCancel = confirmCancelBtn.cloneNode(true);
    confirmCancelBtn.parentNode.replaceChild(newCancel, confirmCancelBtn);

    // wire up the new buttons
    newConfirm.addEventListener('click', () => {
      confirmModal.style.display = 'none';
      onConfirm && onConfirm();
    });

    newCancel.addEventListener('click', () => {
      confirmModal.style.display = 'none';
    });
  }

  // expose closeConfirmModal for possible inline use
  function closeConfirmModal() {
    if (confirmModal) confirmModal.style.display = 'none';
  }

  // ==========================
  // INITIALIZE ON LOAD
  // ==========================
  document.addEventListener('DOMContentLoaded', () => {
    renderUsers();
  });

  // Accessibility: allow Escape to close modal/dropdowns
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      // close add user modal
      if (addUserModal && addUserModal.classList.contains('show')) closeAddUserModal();
      // close role dropdowns
      document.querySelectorAll('.admin-role-dropdown.show').forEach(d => d.classList.remove('show'));
      // close user dropdown
      userDropdown && userDropdown.classList.remove('show');
      // close confirm modal
      confirmModal && (confirmModal.style.display = 'none');
    }
  });