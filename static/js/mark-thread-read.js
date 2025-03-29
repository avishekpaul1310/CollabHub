// Mark thread as read functionality
document.addEventListener('DOMContentLoaded', function() {
    // Check for mark-all-read button
    const markAllReadBtn = document.getElementById('mark-all-read');
    if (!markAllReadBtn) return;
    
    // Get thread ID from button data attribute
    const threadId = markAllReadBtn.getAttribute('data-thread-id');
    if (!threadId) {
        console.error('Thread ID not found on mark-all-read button');
        return;
    }
    
    // Add click handler
    markAllReadBtn.addEventListener('click', function(e) {
        e.preventDefault();
        
        // Show loading state
        const originalText = markAllReadBtn.innerHTML;
        markAllReadBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Marking as read...';
        markAllReadBtn.disabled = true;
        
        // Get CSRF token
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (!csrfToken) {
            console.error('CSRF token not found');
            markAllReadBtn.innerHTML = originalText;
            markAllReadBtn.disabled = false;
            return;
        }
        
        // Make API call to mark thread as read
        fetch(`/api/thread/${threadId}/mark-read/`, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // Show success state
            markAllReadBtn.innerHTML = '<i class="fas fa-check"></i> Marked as read';
            markAllReadBtn.classList.remove('btn-primary');
            markAllReadBtn.classList.add('btn-success');
            
            // Update unread counter in the UI if it exists
            const unreadCounter = document.querySelector('.unread-counter');
            if (unreadCounter && data.read_count > 0) {
                const currentCount = parseInt(unreadCounter.textContent);
                if (!isNaN(currentCount)) {
                    const newCount = Math.max(0, currentCount - data.read_count);
                    unreadCounter.textContent = newCount;
                    
                    // Hide counter if 0
                    if (newCount === 0) {
                        unreadCounter.style.display = 'none';
                    }
                }
            }
            
            // Reset button after 3 seconds
            setTimeout(() => {
                markAllReadBtn.innerHTML = originalText;
                markAllReadBtn.classList.remove('btn-success');
                markAllReadBtn.classList.add('btn-primary');
                markAllReadBtn.disabled = false;
            }, 3000);
        })
        .catch(error => {
            console.error('Error marking thread as read:', error);
            // Show error state
            markAllReadBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
            markAllReadBtn.classList.remove('btn-primary');
            markAllReadBtn.classList.add('btn-danger');
            
            // Reset button after 3 seconds
            setTimeout(() => {
                markAllReadBtn.innerHTML = originalText;
                markAllReadBtn.classList.remove('btn-danger');
                markAllReadBtn.classList.add('btn-primary');
                markAllReadBtn.disabled = false;
            }, 3000);
        });
    });
});