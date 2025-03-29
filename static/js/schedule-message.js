// Schedule message functionality
document.addEventListener('DOMContentLoaded', function() {
    // Set up schedule message button
    const scheduleMessageBtn = document.querySelector('.schedule-message-btn');
    if (!scheduleMessageBtn) return;
    
    // Open modal when button is clicked
    scheduleMessageBtn.addEventListener('click', function(e) {
        e.preventDefault();
        
        // Get the current message content if any
        const messageInput = document.getElementById('message-input');
        const scheduleContent = document.getElementById('schedule-content');
        
        if (messageInput && scheduleContent && messageInput.value.trim()) {
            scheduleContent.value = messageInput.value.trim();
        }
        
        // Set default datetime to tomorrow at 9 AM
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        tomorrow.setHours(9, 0, 0, 0);
        
        // Format for datetime-local input (YYYY-MM-DDTHH:MM)
        const year = tomorrow.getFullYear();
        const month = String(tomorrow.getMonth() + 1).padStart(2, '0');
        const day = String(tomorrow.getDate()).padStart(2, '0');
        const hours = String(tomorrow.getHours()).padStart(2, '0');
        const minutes = String(tomorrow.getMinutes()).padStart(2, '0');
        
        const formattedDate = `${year}-${month}-${day}T${hours}:${minutes}`;
        const scheduleTime = document.getElementById('schedule-time');
        
        if (scheduleTime) {
            scheduleTime.value = formattedDate;
        }
        
        // Open the modal
        const modal = document.getElementById('scheduleMessageModal');
        if (modal) {
            try {
                const bsModal = new bootstrap.Modal(modal);
                bsModal.show();
            } catch (error) {
                console.error('Error showing modal:', error);
                // Fallback - redirect to dedicated page if modal fails
                const workItemId = modal.getAttribute('data-work-item-id');
                if (workItemId) {
                    window.location.href = `/work-item/${workItemId}/schedule-message/`;
                }
            }
        }
    });
    
    // Handle form submission
    const scheduleForm = document.getElementById('scheduleMessageForm');
    if (scheduleForm) {
        scheduleForm.addEventListener('submit', function(e) {
            // Add client-side validation
            const scheduleContent = document.getElementById('schedule-content');
            const scheduleTime = document.getElementById('schedule-time');
            
            if (scheduleContent && !scheduleContent.value.trim()) {
                e.preventDefault();
                alert('Please enter a message to schedule.');
                return;
            }
            
            if (scheduleTime) {
                const selectedTime = new Date(scheduleTime.value);
                const now = new Date();
                
                if (selectedTime <= now) {
                    e.preventDefault();
                    alert('Scheduled time must be in the future.');
                    return;
                }
            }
            
            // Form will submit normally if all validations pass
            // Clear message input if it was copied
            const messageInput = document.getElementById('message-input');
            if (messageInput && scheduleContent && 
                messageInput.value.trim() === scheduleContent.value.trim()) {
                messageInput.value = '';
            }
        });
    }
    
    // Handle preset time buttons
    const presetButtons = document.querySelectorAll('.scheduling-preset-btn');
    if (presetButtons.length > 0) {
        presetButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                
                const preset = this.getAttribute('data-preset');
                if (!preset) return;
                
                const scheduleTime = document.getElementById('schedule-time');
                if (!scheduleTime) return;
                
                const now = new Date();
                let scheduledTime = new Date();
                
                // Calculate time based on preset
                switch(preset) {
                    case 'later-today':
                        // Set to 2 hours from now
                        scheduledTime.setHours(now.getHours() + 2);
                        break;
                        
                    case 'tomorrow-morning':
                        // Set to 9 AM tomorrow
                        scheduledTime.setDate(now.getDate() + 1);
                        scheduledTime.setHours(9, 0, 0, 0);
                        break;
                        
                    case 'tomorrow-afternoon':
                        // Set to 2 PM tomorrow
                        scheduledTime.setDate(now.getDate() + 1);
                        scheduledTime.setHours(14, 0, 0, 0);
                        break;
                        
                    case 'next-week':
                        // Set to next Monday at 9 AM
                        const daysUntilMonday = 1 + (7 - now.getDay()) % 7;
                        scheduledTime.setDate(now.getDate() + daysUntilMonday);
                        scheduledTime.setHours(9, 0, 0, 0);
                        break;
                }
                
                // Format for datetime-local input (YYYY-MM-DDTHH:MM)
                const year = scheduledTime.getFullYear();
                const month = String(scheduledTime.getMonth() + 1).padStart(2, '0');
                const day = String(scheduledTime.getDate()).padStart(2, '0');
                const hours = String(scheduledTime.getHours()).padStart(2, '0');
                const minutes = String(scheduledTime.getMinutes()).padStart(2, '0');
                
                scheduleTime.value = `${year}-${month}-${day}T${hours}:${minutes}`;
            });
        });
    }
});