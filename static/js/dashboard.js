document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Handle work item type selection in the form
    const typeSelect = document.getElementById('id_type');
    if (typeSelect) {
        typeSelect.addEventListener('change', function() {
            updateFormBasedOnType(this.value);
        });
        
        // Initialize form based on current selection
        if (typeSelect.value) {
            updateFormBasedOnType(typeSelect.value);
        }
    }
    
    // Toggle sidebar on mobile
    const sidebarToggle = document.getElementById('sidebar-toggle');
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function() {
            document.getElementById('sidebar').classList.toggle('show');
        });
    }
    
    /**
     * Update form fields based on selected work item type
     */
    function updateFormBasedOnType(type) {
        const descriptionField = document.getElementById('id_description');
        const collaboratorsSection = document.querySelector('.collaborators-section');
        
        if (!descriptionField) return;
        
        // Adjust form based on type
        switch(type) {
            case 'task':
                descriptionField.setAttribute('placeholder', 'Describe the task to be completed...');
                descriptionField.setAttribute('rows', '3');
                break;
            case 'doc':
                descriptionField.setAttribute('placeholder', 'Write your document content here...');
                descriptionField.setAttribute('rows', '10');
                break;
            case 'project':
                descriptionField.setAttribute('placeholder', 'Describe the project goals, timeline, and deliverables...');
                descriptionField.setAttribute('rows', '6');
                break;
        }
        
        // Show collaborators section for projects and documents
        if (collaboratorsSection) {
            if (type === 'project' || type === 'doc') {
                collaboratorsSection.style.display = 'block';
            } else {
                collaboratorsSection.style.display = 'none';
            }
        }
    }
});