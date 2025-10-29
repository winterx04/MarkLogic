document.getElementById("signinForm").addEventListener("submit", function(event) {
    // We DON'T prevent the default action right away.
    // We will only stop it if we find an error.

    let email = document.getElementById("email").value.trim();
    let password = document.getElementById("password").value.trim();
    let isValid = true;

    // Reset previous error messages
    document.getElementById("emailError").textContent = "";
    document.getElementById("passwordError").textContent = "";

    // Email validation
    if (!email) {
        document.getElementById("emailError").textContent = "Email is required.";
        isValid = false;
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        document.getElementById("emailError").textContent = "Enter a valid email address.";
        isValid = false;
    }

    // Password validation
    if (!password) {
        document.getElementById("passwordError").textContent = "Password is required.";
        isValid = false;
    } else if (password.length < 6) {
        document.getElementById("passwordError").textContent = "Password must be at least 6 characters.";
        isValid = false;
    }

    // --- THIS IS THE KEY CHANGE ---
    // If the form is NOT valid, we stop the submission.
    if (!isValid) {
        event.preventDefault(); // Stop the form ONLY if there's a validation error.
    }
    
    // We REMOVE the "if (valid) { ... }" block entirely.
    // If the script gets to this point and the form is valid,
    // it will automatically submit to the 'action' URL specified in your HTML form,
    // which is your Flask backend.
});