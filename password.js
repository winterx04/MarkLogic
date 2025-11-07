// Elements
const passwordInput = document.getElementById('passwordInput');
const confirmPasswordInput = document.getElementById('confirmPasswordInput');
const togglePassword = document.getElementById('togglePassword');
const toggleConfirmPassword = document.getElementById('toggleConfirmPassword');
const passwordError = document.getElementById('passwordError');
const confirmPasswordError = document.getElementById('confirmPasswordError');
const passwordStrength = document.getElementById('passwordStrength');
const strengthBar = document.getElementById('strengthBar');
const strengthText = document.getElementById('strengthText');
const passwordRequirements = document.getElementById('passwordRequirements');
const proceedBtn = document.getElementById('proceedBtn');
const passwordForm = document.getElementById('passwordForm');
const successPopup = document.getElementById('successPopup');

// Requirements elements
const reqLength = document.getElementById('reqLength');
const reqUppercase = document.getElementById('reqUppercase');
const reqLowercase = document.getElementById('reqLowercase');
const reqNumber = document.getElementById('reqNumber');
const reqSpecial = document.getElementById('reqSpecial');

// 🔹 Toggle password visibility using Font Awesome
togglePassword.addEventListener('click', () => {
  const type = passwordInput.type === 'password' ? 'text' : 'password';
  passwordInput.type = type;

  togglePassword.innerHTML =
    type === 'password'
      ? '<i class="fa-solid fa-eye"></i>'
      : '<i class="fa-solid fa-eye-slash"></i>';
});

toggleConfirmPassword.addEventListener('click', () => {
  const type = confirmPasswordInput.type === 'password' ? 'text' : 'password';
  confirmPasswordInput.type = type;

  toggleConfirmPassword.innerHTML =
    type === 'password'
      ? '<i class="fa-solid fa-eye"></i>'
      : '<i class="fa-solid fa-eye-slash"></i>';
});

// ✅ The rest of your JS (validation, strength, etc.) stays the same


    // Password validation
    function validatePassword(password) {
      const requirements = {
        length: password.length >= 8,
        uppercase: /[A-Z]/.test(password),
        lowercase: /[a-z]/.test(password),
        number: /[0-9]/.test(password),
        special: /[!@#$%^&*(),.?":{}|<>]/.test(password)
      };

      return requirements;
    }

    // Calculate password strength
    function calculateStrength(requirements) {
      const metCount = Object.values(requirements).filter(Boolean).length;
      
      if (metCount <= 2) return 'weak';
      if (metCount <= 4) return 'medium';
      return 'strong';
    }

    // Update password requirements UI
    function updateRequirements(requirements) {
      const updateReq = (element, met) => {
        if (met) {
          element.classList.add('met');
          element.querySelector('.requirement-icon').textContent = '✓';
        } else {
          element.classList.remove('met');
          element.querySelector('.requirement-icon').textContent = '○';
        }
      };

      updateReq(reqLength, requirements.length);
      updateReq(reqUppercase, requirements.uppercase);
      updateReq(reqLowercase, requirements.lowercase);
      updateReq(reqNumber, requirements.number);
      updateReq(reqSpecial, requirements.special);
    }

    // Check if form is valid
    function checkFormValidity() {
      const password = passwordInput.value;
      const confirmPassword = confirmPasswordInput.value;
      const requirements = validatePassword(password);
      const allRequirementsMet = Object.values(requirements).every(Boolean);
      const passwordsMatch = password === confirmPassword && password.length > 0;

      proceedBtn.disabled = !(allRequirementsMet && passwordsMatch);
    }

    // Password input handler
    passwordInput.addEventListener('input', (e) => {
      const password = e.target.value;

      if (password.length > 0) {
        passwordStrength.classList.add('show');
        passwordRequirements.classList.add('show');

        const requirements = validatePassword(password);
        const strength = calculateStrength(requirements);

        // Update strength bar
        strengthBar.className = 'strength-bar ' + strength;
        
        // Update strength text
        const strengthTexts = {
          weak: 'Weak password',
          medium: 'Medium strength',
          strong: 'Strong password'
        };
        strengthText.textContent = strengthTexts[strength];

        // Update requirements
        updateRequirements(requirements);

        // Clear error
        passwordError.classList.remove('show');
        passwordInput.classList.remove('error');
      } else {
        passwordStrength.classList.remove('show');
        passwordRequirements.classList.remove('show');
      }

      checkFormValidity();
    });

    // Confirm password input handler
    confirmPasswordInput.addEventListener('input', (e) => {
      const password = passwordInput.value;
      const confirmPassword = e.target.value;

      if (confirmPassword.length > 0) {
        if (password !== confirmPassword) {
          confirmPasswordError.textContent = 'Passwords do not match';
          confirmPasswordError.classList.add('show');
          confirmPasswordInput.classList.add('error');
        } else {
          confirmPasswordError.classList.remove('show');
          confirmPasswordInput.classList.remove('error');
        }
      } else {
        confirmPasswordError.classList.remove('show');
        confirmPasswordInput.classList.remove('error');
      }

      checkFormValidity();
    });

    // Form submission
    passwordForm.addEventListener('submit', (e) => {
      e.preventDefault();

      const password = passwordInput.value;
      const confirmPassword = confirmPasswordInput.value;
      const requirements = validatePassword(password);
      const allRequirementsMet = Object.values(requirements).every(Boolean);

      // Validate
      if (!allRequirementsMet) {
        passwordError.textContent = 'Password does not meet all requirements';
        passwordError.classList.add('show');
        passwordInput.classList.add('error');
        return;
      }

      if (password !== confirmPassword) {
        confirmPasswordError.textContent = 'Passwords do not match';
        confirmPasswordError.classList.add('show');
        confirmPasswordInput.classList.add('error');
        return;
      }

      // Success
      console.log('Password created successfully:', password);
      
      // Show success popup
      successPopup.classList.add('show');
      setTimeout(() => {
        successPopup.classList.remove('show');
      }, 3000);

      // Reset form
      setTimeout(() => {
        passwordForm.reset();
        passwordStrength.classList.remove('show');
        passwordRequirements.classList.remove('show');
        proceedBtn.disabled = true;
      }, 1500);
    });