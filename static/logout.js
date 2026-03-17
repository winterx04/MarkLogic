// =========================================================================
// logout.js - Handles the top-right user icon and dropdown ONLY.
// Depends on utils.js for the showConfirmModal function.
// =========================================================================
document.addEventListener('DOMContentLoaded', () => {
    const userIcon = document.getElementById('userIcon');
    const userDropdown = document.getElementById('userDropdown');
    const logoutItem = document.getElementById('logoutItem');

    if (userIcon && userDropdown) {
        userIcon.addEventListener('click', (e) => {
            e.stopPropagation();
            userDropdown.classList.toggle('show');
        });

        if (logoutItem) {
            logoutItem.addEventListener('click', () => {
                // This function now comes from utils.js
                showConfirmModal('Are you sure you want to log out?', () => {
                    window.location.href = '/logout';
                });
            });
        }
    }

    document.addEventListener('click', (e) => {
        if (userDropdown && userDropdown.classList.contains('show')) {
            if (!userDropdown.contains(e.target) && !userIcon.contains(e.target)) {
                userDropdown.classList.remove('show');
            }
        }
    });
});