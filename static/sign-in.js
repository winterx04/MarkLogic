// =========================================================================
// sign-in.js - Robust Client-Side Format Validation
// =========================================================================
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('signinForm');
    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    const emailError = document.getElementById('emailError');
    const passwordError = document.getElementById('passwordError');

    if (!form) {
        return; // Stop if the form doesn't exist on the page
    }

    form.addEventListener('submit', (event) => {
        // --- 1. Reset all previous errors ---
        emailError.textContent = '';
        passwordError.textContent = '';
        emailInput.classList.remove('error-input'); // Visually remove error state
        passwordInput.classList.remove('error-input'); // Visually remove error state

        // --- 2. Perform Validation ---
        let isEmailValid = validateEmail();
        let isPasswordValid = validatePassword();

        // --- 3. Final Decision ---
        // If either validation function returns false, stop the form submission.
        if (!isEmailValid || !isPasswordValid) {
            event.preventDefault(); 
        }
    });

    function validateEmail() {
        const email = emailInput.value.trim();
        // A robust and commonly used regex for email format
        const emailRegex = /^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}$/;

        if (email === '') {
            emailError.textContent = 'Email is required.';
            emailInput.classList.add('error-input'); // Visually highlight the input
            return false;
        } else if (!emailRegex.test(email)) {
            emailError.textContent = 'Please enter a valid email address.';
            emailInput.classList.add('error-input'); // Visually highlight the input
            return false;
        }
        return true;
    }

    function validatePassword() {
        const password = passwordInput.value.trim();
        if (password === '') {
            passwordError.textContent = 'Password is required.';
            passwordInput.classList.add('error-input'); // Visually highlight the input
            return false;
        }
        return true;
    }
});