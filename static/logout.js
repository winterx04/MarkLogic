// This file controls the user icon dropdown and logout functionality ONLY.
document.addEventListener('DOMContentLoaded', () => {
    
    // --- Get elements for the user dropdown ---
    const userIcon = document.getElementById('userIcon');
    const userDropdown = document.getElementById('userDropdown');
    const logoutItem = document.getElementById('logoutItem');

    // Make sure the elements exist before adding listeners
    if (userIcon && userDropdown) {
        // --- Toggle the dropdown menu on icon click ---
        userIcon.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevents the global click listener from immediately closing it
            userDropdown.classList.toggle('show');
        });

        // --- Handle Logout Click ---
        if (logoutItem) {
            logoutItem.addEventListener('click', () => {
                // Use a simple built-in confirm for reliability
                if (window.confirm('Are you sure you want to log out?')) {
                    // Redirect to the Flask logout route
                    window.location.href = '/logout';
                }
            });
        }
    }

    // --- Global click listener to close the dropdown when clicking outside ---
    document.addEventListener('click', (e) => {
        if (userDropdown && userDropdown.classList.contains('show')) {
            if (!userDropdown.contains(e.target) && !userIcon.contains(e.target)) {
                userDropdown.classList.remove('show');
            }
        }
    });
});