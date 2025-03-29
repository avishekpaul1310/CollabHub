// Add to static/js/schedule-message.js

document.addEventListener('DOMContentLoaded', function() {
    // Set up schedule message button
    const scheduleMessageBtn = document.querySelector('.schedule-message-btn');
    if (!scheduleMessageBtn) return;
    
    // Open modal when button is clicked
    scheduleMessageBtn.addEventListener('click', function() {
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
        
        // Format for datetime-local input
        const formattedDate = tomorrow.toISOString().slice(0, 16); // YYYY-MM-DDTHH:MM
        document.getElementById('schedule-time').value = formattedDate;
        
        // Open the modal
        const modal = new bootstrap.Modal(document.getElementById('scheduleMessageModal'));
        modal.show();
    });
    
    // Handle form submission
    const scheduleForm = document.getElementById('scheduleMessageForm');
    if (scheduleForm) {
        scheduleForm.addEventListener('submit', function(e) {
            // Form will submit normally, but clear message input if it was copied
            const messageInput = document.getElementById('message-input');
            const scheduleContent = document.getElementById('schedule-content');
            
            if (messageInput && scheduleContent && 
                messageInput.value.trim() === scheduleContent.value.trim()) {
                messageInput.value = '';
            }
        });
    }
});