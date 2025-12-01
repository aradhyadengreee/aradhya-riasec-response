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
        const result = await response.json();
        
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
    container.insertBefore(alertDiv, container.firstChild);
    
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
    container.insertBefore(alertDiv, container.firstChild);
    
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
        button.innerHTML = '<span class="loading-spinner"></span> Loading...';
        button.setAttribute('data-original-text', originalText);
    } else {
        button.disabled = false;
        const originalText = button.getAttribute('data-original-text');
        if (originalText) {
            button.innerHTML = originalText;
        }
    }
}



// Results page functions
async function generateRecommendations() {
    try {
        const generateButton = document.getElementById('generateRecommendations');
        if (generateButton) setLoadingState(generateButton, true);
        
        const result = await apiCall('/api/recommendations/generate', 'POST');
        
        displayRecommendations(result.recommendations);
        showSuccess('Recommendations generated successfully!');
        
    } catch (error) {
        showError('Failed to generate recommendations: ' + error.message);
    } finally {
        const generateButton = document.getElementById('generateRecommendations');
        if (generateButton) setLoadingState(generateButton, false);
    }
}

function displayRecommendations(recommendations) {
    const container = document.getElementById('recommendationsContainer');
    
    if (!container) return;
    
    if (recommendations.length === 0) {
        container.innerHTML = '<div class="alert alert-info">No recommendations found. Please try adjusting your profile.</div>';
        return;
    }
    
    container.innerHTML = recommendations.map(job => `
        <div class="card job-card fade-in">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <h5 class="card-title">${job.job_title}</h5>
                        <h6 class="card-subtitle mb-2 text-muted">${job.family_title}</h6>
                    </div>
                    <div class="match-percentage">${job.match_percentage}%</div>
                </div>
                
                <p class="card-text">${job.job_description || 'No description available.'}</p>
                
                <div class="row mt-3">
                    <div class="col-md-6">
                        <strong>RIASEC Code:</strong> ${job.riasec_code}<br>
                        <strong>Salary Range:</strong> ${job.salary_range}<br>
                        <strong>Market Demand:</strong> ${job.market_demand}
                    </div>
                    <div class="col-md-6">
                        <strong>Growth Projection:</strong> ${job.growth_projection}<br>
                        <strong>Learning Path:</strong> ${job.learning_pathway || 'Not specified'}
                    </div>
                </div>
                
                ${job.primary_skills && job.primary_skills.length > 0 ? `
                <div class="mt-3">
                    <strong>Key Skills:</strong>
                    <ul class="skills-list">
                        ${job.primary_skills.map(skill => `<li>${skill}</li>`).join('')}
                    </ul>
                </div>
                ` : ''}
                
                <div class="mt-3">
                    <small class="text-muted">${job.reasoning || 'Good match based on your profile and interests.'}</small>
                </div>
            </div>
        </div>
    `).join('');
}