// main.js (FIXED VERSION)
// Main JavaScript for Career Counseling App

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Question navigation
    initializeQuestionNavigation();
    
    // Interest selection
    initializeInterestSelection();
    
    // Form validation
    initializeFormValidation();
});

function initializeQuestionNavigation() {
    const optionCards = document.querySelectorAll('.option-card');
    
    optionCards.forEach(card => {
        card.addEventListener('click', function() {
            // Remove selected class from all options
            optionCards.forEach(c => c.classList.remove('selected'));
            
            // Add selected class to clicked option
            this.classList.add('selected');
            
            // Check the radio button
            const radio = this.querySelector('input[type="radio"]');
            if (radio) {
                radio.checked = true;
            }
        });
    });
}

function initializeInterestSelection() {
    const interestCheckboxes = document.querySelectorAll('.interest-checkbox');
    const selectedCount = document.getElementById('selectedCount');
    
    function updateSelectedCount() {
        const selected = document.querySelectorAll('.interest-checkbox:checked').length;
        if (selectedCount) {
            selectedCount.textContent = `${selected} selected`;
            
            // Update styling based on count
            if (selected < 3) {
                selectedCount.className = 'text-warning';
            } else if (selected > 5) {
                selectedCount.className = 'text-danger';
            } else {
                selectedCount.className = 'text-success';
            }
        }
    }
    
    interestCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const label = this.closest('.interest-label');
            if (this.checked) {
                label.classList.add('selected');
            } else {
                label.classList.remove('selected');
            }
            updateSelectedCount();
        });
    });
    
    updateSelectedCount();
}

function initializeFormValidation() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!this.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
            }
            this.classList.add('was-validated');
        });
    });
}

// API Helper Functions
async function apiCall(url, method = 'GET', data = null) {
    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json',
        }
    };
    
    if (data && (method === 'POST' || method === 'PUT')) {
        options.body = JSON.stringify(data);
    }
    
    try {
        const response = await fetch(url, options);
        
        // Check if response is empty
        const responseText = await response.text();
        if (!responseText || responseText.trim() === '') {
            throw new Error('Server returned empty response');
        }
        
        const result = JSON.parse(responseText);
        
        if (!response.ok) {
            throw new Error(result.error || 'API request failed');
        }
        
        return result;
    } catch (error) {
        console.error('API call failed:', error);
        showError(error.message);
        throw error;
    }
}

function showError(message) {
    // Create error alert
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-danger alert-dismissible fade show';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // Add to page
    const container = document.querySelector('.container');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
    } else {
        document.body.insertBefore(alertDiv, document.body.firstChild);
    }
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

function showSuccess(message) {
    // Create success alert
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-success alert-dismissible fade show';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // Add to page
    const container = document.querySelector('.container');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
    } else {
        document.body.insertBefore(alertDiv, document.body.firstChild);
    }
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

// Loading state management
function setLoadingState(button, isLoading) {
    if (isLoading) {
        button.disabled = true;
        const originalText = button.innerHTML;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Loading...';
        button.setAttribute('data-original-text', originalText);
    } else {
        button.disabled = false;
        const originalText = button.getAttribute('data-original-text');
        if (originalText) {
            button.innerHTML = originalText;
        }
    }
}

// Helper function to get color based on match percentage
function getMatchColor(percentage) {
    if (percentage >= 80) return '#2ecc71'; // Green
    if (percentage >= 60) return '#3498db'; // Blue
    if (percentage >= 40) return '#f39c12'; // Orange
    return '#e74c3c'; // Red
}