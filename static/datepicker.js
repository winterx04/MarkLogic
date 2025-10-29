class CustomDatePicker {
  constructor(inputElement) {
    this.input = inputElement;
    this.selectedDate = null;
    this.currentMonth = new Date().getMonth();
    this.currentYear = new Date().getFullYear();
    this.calendar = null;
    
    this.init();
  }

  init() {
    // Wrap input in container
    const wrapper = document.createElement('div');
    wrapper.className = 'custom-datepicker-wrapper';
    this.input.parentNode.insertBefore(wrapper, this.input);
    wrapper.appendChild(this.input);
    
    // Create calendar element
    this.calendar = document.createElement('div');
    this.calendar.className = 'custom-datepicker-calendar';
    wrapper.appendChild(this.calendar);
    
    // Add click event to input
    this.input.addEventListener('click', (e) => {
      e.stopPropagation();
      this.show();
    });
    
    // Close calendar when clicking outside
    document.addEventListener('click', (e) => {
      if (!wrapper.contains(e.target)) {
        this.hide();
      }
    });
    
    // Prevent calendar from closing when clicking inside it
    this.calendar.addEventListener('click', (e) => {
      e.stopPropagation();
    });
    
    this.render();
  }

  show() {
    this.calendar.classList.add('show');
  }

  hide() {
    this.calendar.classList.remove('show');
  }

  render() {
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                        'July', 'August', 'September', 'October', 'November', 'December'];
    
    this.calendar.innerHTML = `
      <div class="datepicker-header">
        <button class="datepicker-nav-btn" data-action="prev">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"></polyline>
          </svg>
        </button>
        <div class="datepicker-month-year">
          ${monthNames[this.currentMonth]} ${this.currentYear}
        </div>
        <button class="datepicker-nav-btn" data-action="next">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 18 15 12 9 6"></polyline>
          </svg>
        </button>
      </div>
      
      <div class="datepicker-weekdays">
        <div class="datepicker-weekday">Su</div>
        <div class="datepicker-weekday">Mo</div>
        <div class="datepicker-weekday">Tu</div>
        <div class="datepicker-weekday">We</div>
        <div class="datepicker-weekday">Th</div>
        <div class="datepicker-weekday">Fr</div>
        <div class="datepicker-weekday">Sa</div>
      </div>
      
      <div class="datepicker-days"></div>
      
      <div class="datepicker-actions">
        <button class="datepicker-btn" data-action="clear">Clear</button>
        <button class="datepicker-btn primary" data-action="today">Today</button>
      </div>
    `;
    
    this.renderDays();
    this.attachEventListeners();
  }

  renderDays() {
    const daysContainer = this.calendar.querySelector('.datepicker-days');
    daysContainer.innerHTML = '';
    
    const firstDay = new Date(this.currentYear, this.currentMonth, 1).getDay();
    const daysInMonth = new Date(this.currentYear, this.currentMonth + 1, 0).getDate();
    const daysInPrevMonth = new Date(this.currentYear, this.currentMonth, 0).getDate();
    
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    // Previous month days
    for (let i = firstDay - 1; i >= 0; i--) {
      const day = daysInPrevMonth - i;
      const dayElement = document.createElement('div');
      dayElement.className = 'datepicker-day other-month';
      dayElement.textContent = day;
      daysContainer.appendChild(dayElement);
    }
    
    // Current month days
    for (let day = 1; day <= daysInMonth; day++) {
      const dayElement = document.createElement('div');
      dayElement.className = 'datepicker-day';
      dayElement.textContent = day;
      dayElement.dataset.day = day;
      
      const currentDate = new Date(this.currentYear, this.currentMonth, day);
      currentDate.setHours(0, 0, 0, 0);
      
      // Check if today
      if (currentDate.getTime() === today.getTime()) {
        dayElement.classList.add('today');
      }
      
      // Check if selected
      if (this.selectedDate) {
        const selected = new Date(this.selectedDate);
        selected.setHours(0, 0, 0, 0);
        if (currentDate.getTime() === selected.getTime()) {
          dayElement.classList.add('selected');
        }
      }
      
      daysContainer.appendChild(dayElement);
    }
    
    // Next month days
    const totalCells = daysContainer.children.length;
    const remainingCells = 42 - totalCells; // 6 rows * 7 days
    for (let day = 1; day <= remainingCells; day++) {
      const dayElement = document.createElement('div');
      dayElement.className = 'datepicker-day other-month';
      dayElement.textContent = day;
      daysContainer.appendChild(dayElement);
    }
  }

  attachEventListeners() {
    // Navigation buttons
    this.calendar.querySelector('[data-action="prev"]').addEventListener('click', () => {
      this.currentMonth--;
      if (this.currentMonth < 0) {
        this.currentMonth = 11;
        this.currentYear--;
      }
      this.render();
    });
    
    this.calendar.querySelector('[data-action="next"]').addEventListener('click', () => {
      this.currentMonth++;
      if (this.currentMonth > 11) {
        this.currentMonth = 0;
        this.currentYear++;
      }
      this.render();
    });
    
    // Day selection
    this.calendar.querySelectorAll('.datepicker-day:not(.other-month)').forEach(day => {
      day.addEventListener('click', () => {
        const dayNum = parseInt(day.dataset.day);
        this.selectDate(new Date(this.currentYear, this.currentMonth, dayNum));
      });
    });
    
    // Action buttons
    this.calendar.querySelector('[data-action="clear"]').addEventListener('click', () => {
      this.selectedDate = null;
      this.input.value = '';
      this.hide();
    });
    
    this.calendar.querySelector('[data-action="today"]').addEventListener('click', () => {
      this.selectDate(new Date());
    });
  }

  selectDate(date) {
    this.selectedDate = date;
    this.currentMonth = date.getMonth();
    this.currentYear = date.getFullYear();
    
    // Format date as YYYY-MM-DD
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    this.input.value = `${day}-${month}-${year}`;
    
    this.render();
    this.hide();
    
    // Trigger change event
    this.input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  getValue() {
    return this.input.value;
  }

  setValue(dateString) {
    if (dateString) {
      this.selectedDate = new Date(dateString);
      this.currentMonth = this.selectedDate.getMonth();
      this.currentYear = this.selectedDate.getFullYear();
      this.input.value = dateString;
      this.render();
    }
  }
}

// Initialize custom date pickers
document.addEventListener('DOMContentLoaded', () => {
  // Replace standard date inputs with custom date pickers
  const dateInputs = document.querySelectorAll('input[type="date"]');
  dateInputs.forEach(input => {
    // Change input type to text and add icon
    input.type = 'text';
    input.classList.add('custom-datepicker-input');
    input.readOnly = true;
    input.placeholder = 'Select date';
    
    // Add calendar icon
    const icon = document.createElement('div');
    icon.innerHTML = `
      <svg class="datepicker-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
        <line x1="16" y1="2" x2="16" y2="6"></line>
        <line x1="8" y1="2" x2="8" y2="6"></line>
        <line x1="3" y1="10" x2="21" y2="10"></line>
      </svg>
    `;
    
    // Initialize custom date picker
    new CustomDatePicker(input);
  });
});