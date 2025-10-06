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
